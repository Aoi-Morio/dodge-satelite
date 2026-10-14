using System.Globalization;
using System.Text.Json;

namespace DodgeSatelite.Gate;

public sealed record SiteInput(double LatitudeDeg, double LongitudeDeg, double ElevationM, string Name);
public sealed record TargetInput(double RaDeg, double DecDeg, string Name);
public sealed record EquipmentInput(double FocalLengthMm, double SensorWidthMm, double SensorHeightMm);
public sealed record ObservationConfig(
    SiteInput Site, TargetInput Target, EquipmentInput Equipment, string Start, string End,
    double ExposureS, double ReadoutS = 0, double SampleS = 1, double PaddingS = 3,
    double AngularMarginDeg = 0.1, double MinTargetAltDeg = 25, double MaxSunAltDeg = -12,
    bool SunlitOnly = true, double MaxEpochAgeDays = 2);
public sealed record ForecastRequest(int SchemaVersion, string RequestId, ObservationConfig Config,
    string Group = "visual", bool Offline = false);
public sealed record ForecastWindow(string StartUtc, string EndUtc);
public sealed record ForecastResponse(
    int SchemaVersion, string RequestId, string Status, string? Error,
    string GeneratedAtUtc, string SessionStartUtc, string ValidUntilUtc,
    ForecastWindow[] Windows, int SatelliteCount, string CatalogSha256, string[] Warnings);
public sealed record TimeWindow(DateTimeOffset Start, DateTimeOffset End);
public sealed record Forecast(ForecastResponse Response, TimeWindow Session,
    DateTimeOffset GeneratedAt, IReadOnlyList<TimeWindow> Windows);

public static class Protocol {
    public static JsonSerializerOptions Json { get; } = new() {
        PropertyNamingPolicy = JsonNamingPolicy.SnakeCaseLower,
        PropertyNameCaseInsensitive = false,
        MaxDepth = 32
    };

    // Python datetime carries six fractional digits, whereas .NET has seven.
    // Normalize requests before exact session matching, never silently tolerate a different session.
    public static string Utc(DateTimeOffset time) => time.ToUniversalTime().ToString("yyyy-MM-dd'T'HH:mm:ss.ffffff'Z'", CultureInfo.InvariantCulture);

    public static DateTimeOffset ParseUtc(string? value) {
        if (string.IsNullOrEmpty(value) ||
            !(value.EndsWith('Z') || value.EndsWith("+00:00", StringComparison.Ordinal)) ||
            !DateTimeOffset.TryParse(value, CultureInfo.InvariantCulture,
                DateTimeStyles.RoundtripKind, out var parsed) || parsed.Offset != TimeSpan.Zero) {
            throw new InvalidDataException("Engine returned an invalid explicit UTC timestamp.");
        }
        return parsed;
    }

    public static Forecast Validate(string json, ForecastRequest request, DateTimeOffset now) {
        var response = JsonSerializer.Deserialize<ForecastResponse>(json, Json)
            ?? throw new InvalidDataException("Engine returned an empty response.");
        if (response.SchemaVersion != 1 || response.RequestId != request.RequestId) {
            throw new InvalidDataException("Engine protocol/request identifier mismatch.");
        }
        if (response.Status != "ok") {
            throw new InvalidOperationException(response.Error ?? "Satellite prediction failed. No exposure started.");
        }
        var start = ParseUtc(response.SessionStartUtc);
        var end = ParseUtc(response.ValidUntilUtc);
        var generated = ParseUtc(response.GeneratedAtUtc);
        if (start != ParseUtc(request.Config.Start) || end != ParseUtc(request.Config.End) ||
            end <= start || end <= now || generated > now.AddSeconds(5) ||
            generated < now.AddMinutes(-2)) {
            throw new InvalidDataException("Forecast is expired, clock-inconsistent or for a different session.");
        }
        if (response.SatelliteCount <= 0 || response.CatalogSha256 is null ||
            response.CatalogSha256.Length != 64 ||
            !response.CatalogSha256.All(Uri.IsHexDigit) || response.Windows is null ||
            response.Windows.Length > 10000 || response.Warnings is null) {
            throw new InvalidDataException("Forecast is missing catalog provenance or valid intervals.");
        }
        var windows = new List<TimeWindow>();
        var previous = start;
        foreach (var window in response.Windows) {
            var a = ParseUtc(window.StartUtc);
            var b = ParseUtc(window.EndUtc);
            if (a < previous || a < start || b > end || a >= b) {
                throw new InvalidDataException("Engine windows overlap or exceed the forecast session.");
            }
            windows.Add(new(a, b));
            previous = b;
        }
        return new(response, new(start, end), generated, windows);
    }

    public static DateTimeOffset? NextStart(Forecast forecast, DateTimeOffset now,
        double exposureSeconds, double guardSeconds) {
        if (!double.IsFinite(exposureSeconds) || exposureSeconds <= 0 ||
            !double.IsFinite(guardSeconds) || guardSeconds < 0) {
            throw new ArgumentOutOfRangeException(nameof(exposureSeconds));
        }
        foreach (var window in forecast.Windows) {
            var start = now > window.Start.AddSeconds(guardSeconds) ? now : window.Start.AddSeconds(guardSeconds);
            if (start.AddSeconds(exposureSeconds + guardSeconds) <= window.End) return start;
        }
        return null;
    }
}
