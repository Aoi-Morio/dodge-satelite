using System.ComponentModel.Composition;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Text.Json;
using DodgeSatelite.Gate;
using Newtonsoft.Json;
using NINA.Astrometry;
using NINA.Core.Enum;
using NINA.Core.Model;
using NINA.Core.Model.Equipment;
using NINA.Core.Utility;
using NINA.Equipment.Interfaces.Mediator;
using NINA.Profile.Interfaces;
using NINA.Sequencer.SequenceItem;
using NINA.Sequencer.SequenceItem.Imaging;
using NINA.Sequencer.Utility;
using NINA.Sequencer.Validations;
using NINA.WPF.Base.Interfaces.Mediator;
using NINA.WPF.Base.Interfaces.ViewModel;

namespace DodgeSatelite.NINA;

[Export(typeof(ISequenceItem))]
[ExportMetadata("Name", "dodge satelite: Satellite-aware Exposure")]
[ExportMetadata("Description", "Wait for a predicted satellite window, then take one NINA light exposure. Experimental; catalog-limited.")]
[ExportMetadata("Category", "dodge satelite")]
[ExportMetadata("Icon", "CameraSVG")]
[JsonObject(MemberSerialization.OptIn)]
public sealed class SatelliteAwareExposure : TakeExposure, IValidatable {
    private readonly IProfileService profiles;
    private readonly ICameraMediator camera;
    private readonly IImagingMediator imaging;
    private readonly IImageSaveMediator saver;
    private readonly IImageHistoryVM history;
    private ExposureGate? gate;
    private string? gateExecutable;
    private string statusText = "Experimental / 実験版: catalog coverage and orbital errors limit every forecast.";

    [ImportingConstructor]
    public SatelliteAwareExposure(IProfileService profileService, ICameraMediator cameraMediator,
        IImagingMediator imagingMediator, IImageSaveMediator imageSaveMediator, IImageHistoryVM imageHistoryVM)
        : base(profileService, cameraMediator, imagingMediator, imageSaveMediator, imageHistoryVM) {
        (profiles, camera, imaging, saver, history) =
            (profileService, cameraMediator, imagingMediator, imageSaveMediator, imageHistoryVM);
        ExposureTime = 120;
        Binning = new BinningMode(1, 1);
        ImageType = "LIGHT";
        ErrorBehavior = InstructionErrorBehavior.AbortOnError;
    }

    [JsonProperty] public string EnginePath { get; set; } = "";
    [JsonProperty] public string CatalogGroup { get; set; } = "visual";
    [JsonProperty] public bool Offline { get; set; }
    [JsonProperty] public double MaximumWaitMinutes { get; set; } = 10;
    [JsonProperty] public double LookAheadMinutes { get; set; } = 5;
    [JsonProperty] public double MaxEpochAgeDays { get; set; } = 2;
    [JsonProperty] public double AngularMarginDegrees { get; set; } = 0.1;
    [JsonProperty] public double PaddingSeconds { get; set; } = 3;
    [JsonProperty] public double HandoffGuardSeconds { get; set; } = 3;
    [JsonProperty] public double SampleSeconds { get; set; } = 1;
    [JsonProperty] public double MinimumTargetAltitude { get; set; } = 25;
    [JsonProperty] public double MaximumSunAltitude { get; set; } = -12;
    [JsonProperty] public bool SunlitOnly { get; set; } = true;
    [JsonProperty] public double FocalLengthOverrideMm { get; set; }
    [JsonProperty] public double SensorWidthOverrideMm { get; set; }
    [JsonProperty] public double SensorHeightOverrideMm { get; set; }

    public string StatusText { get => statusText; private set { statusText = value; RaisePropertyChanged(); } }

    public string ResolveEnginePath() => string.IsNullOrWhiteSpace(EnginePath)
        ? Path.Combine(Path.GetDirectoryName(typeof(SatellitePlugin).Assembly.Location)!, "Engine", "dodge-satelite-engine.exe")
        : Path.GetFullPath(Environment.ExpandEnvironmentVariables(EnginePath));

    public ObservationConfig BuildObservation(DateTimeOffset now) {
        var context = ItemUtility.RetrieveContextCoordinates(Parent)
            ?? throw new InvalidOperationException("Place this instruction inside a Deep Sky Object sequence with a fixed target.");
        if (context.ShiftTrackingRate?.Enabled == true)
            throw new InvalidOperationException("Non-sidereal/moving-target tracking is not supported by this plugin version.");
        var coordinates = context.Coordinates.Transform(Epoch.J2000);
        var profile = profiles.ActiveProfile;
        var info = camera.GetInfo();
        var pixel = profile.CameraSettings.PixelSize > 0 ? profile.CameraSettings.PixelSize : info.PixelSize;
        var width = SensorWidthOverrideMm > 0 ? SensorWidthOverrideMm : info.XSize * pixel / 1000;
        var height = SensorHeightOverrideMm > 0 ? SensorHeightOverrideMm : info.YSize * pixel / 1000;
        var focal = FocalLengthOverrideMm > 0 ? FocalLengthOverrideMm : profile.TelescopeSettings.FocalLength;
        CheckFinite("Focal length", focal, 0.1, 100000);
        CheckFinite("Sensor width", width, 0.1, 100000);
        CheckFinite("Sensor height", height, 0.1, 100000);
        var horizon = Math.Max(LookAheadMinutes * 60, ExposureTime + 2 * HandoffGuardSeconds + 30);
        CheckFinite("Forecast duration", horizon, 1, 3600);
        return new(
            new(profile.AstrometrySettings.Latitude, profile.AstrometrySettings.Longitude,
                profile.AstrometrySettings.Elevation, "NINA active profile"),
            new(coordinates.RADegrees, coordinates.Dec, "NINA sequence target (J2000)"),
            new(focal, width, height), Protocol.Utc(now), Protocol.Utc(now.AddSeconds(horizon)),
            ExposureTime, SampleS: SampleSeconds, PaddingS: PaddingSeconds,
            AngularMarginDeg: AngularMarginDegrees, MinTargetAltDeg: MinimumTargetAltitude,
            MaxSunAltDeg: MaximumSunAltitude, SunlitOnly: SunlitOnly, MaxEpochAgeDays: MaxEpochAgeDays);
    }

    public static string ContextKey(ObservationConfig config, string group, bool offline) =>
        System.Text.Json.JsonSerializer.Serialize(config with { Start = "", End = "" }, Protocol.Json) + "|" + group + "|" + offline;

    public override async Task Execute(IProgress<ApplicationStatus> progress, CancellationToken token) {
        if (!Validate()) throw new InvalidOperationException(string.Join("; ", Issues));
        var executable = ResolveEnginePath();
        if (gate is null || gateExecutable != executable) {
            gate = new ExposureGate(new EngineClient(executable));
            gateExecutable = executable;
        }
        var elapsed = Stopwatch.StartNew();
        while (true) {
            token.ThrowIfCancellationRequested();
            var config = BuildObservation(DateTimeOffset.UtcNow);
            var context = ContextKey(config, CatalogGroup, Offline);
            var remaining = TimeSpan.FromMinutes(MaximumWaitMinutes) - elapsed.Elapsed;
            if (remaining <= TimeSpan.Zero) throw new TimeoutException("dodge satelite maximum waiting time exceeded.");
            var result = await gate.WaitAsync(context,
                () => new(1, Guid.NewGuid().ToString("N"), BuildObservation(DateTimeOffset.UtcNow), CatalogGroup, Offline),
                ExposureTime, HandoffGuardSeconds, remaining, message => {
                    StatusText = message;
                    progress?.Report(new ApplicationStatus { Status = message });
                }, token);
            // Settings/camera state may have changed while the forecast or wait
            // was running. Recheck LIGHT-only and normal NINA prerequisites.
            if (!Validate()) throw new InvalidOperationException(string.Join("; ", Issues));
            if (!string.Equals(ResolveEnginePath(), executable, StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Prediction engine path changed while waiting. Restart this instruction to use the new engine.");
            var current = BuildObservation(DateTimeOffset.UtcNow);
            if (context != ContextKey(current, CatalogGroup, Offline) ||
                !gate.CanStart(context, ExposureTime, HandoffGuardSeconds)) {
                gate.Invalidate();
                continue;
            }
            token.ThrowIfCancellationRequested();
            if (elapsed.Elapsed > TimeSpan.FromMinutes(MaximumWaitMinutes))
                throw new TimeoutException("dodge satelite maximum waiting time exceeded before exposure.");
            StatusText = $"{result.SatelliteCount} satellites; proposed window / 予測枠で露光 (not guaranteed clear)";
            foreach (var warning in result.Warnings) Logger.Warning("dodge satelite: " + warning);
            // Use NINA's own capture/history/save pipeline and cancellation behavior.
            await base.Execute(progress, token);
            return;
        }
    }

    private static void CheckFinite(string name, double value, double minimum, double maximum) {
        if (!double.IsFinite(value) || value < minimum || value > maximum)
            throw new ArgumentException($"{name} must be between {minimum} and {maximum}.");
    }

    public new bool Validate() {
        base.Validate();
        var issues = new List<string>(Issues);
        try {
            if (ImageType != "LIGHT") throw new ArgumentException("dodge satelite supports LIGHT frames only; use standard NINA instructions for calibration frames.");
            if (!File.Exists(ResolveEnginePath())) throw new FileNotFoundException("Bundled dodge satelite engine is missing. Extract the entire plugin ZIP, including Engine.");
            if (!System.Text.RegularExpressions.Regex.IsMatch(CatalogGroup ?? "", "^[A-Za-z0-9-]{1,64}$"))
                throw new ArgumentException("Enter a valid CelesTrak group (active covers more objects than visual/stations). ");
            CheckFinite("Exposure seconds", ExposureTime, 0.1, 1800);
            CheckFinite("Maximum wait minutes", MaximumWaitMinutes, 0.01, 120);
            CheckFinite("Look-ahead minutes", LookAheadMinutes, 1, 60);
            CheckFinite("Epoch age days", MaxEpochAgeDays, 0.01, 7);
            CheckFinite("Angular margin", AngularMarginDegrees, 0, 10);
            CheckFinite("Time padding", PaddingSeconds, 0, 3600);
            CheckFinite("Handoff guard", HandoffGuardSeconds, 1, 60);
            CheckFinite("Sample seconds", SampleSeconds, 0.05, 2);
            CheckFinite("Minimum target altitude", MinimumTargetAltitude, 0, 90);
            CheckFinite("Maximum Sun altitude", MaximumSunAltitude, -90, 90);
            CheckFinite("Focal length override", FocalLengthOverrideMm, 0, 100000);
            CheckFinite("Sensor width override", SensorWidthOverrideMm, 0, 100000);
            CheckFinite("Sensor height override", SensorHeightOverrideMm, 0, 100000);
            BuildObservation(DateTimeOffset.UtcNow);
        } catch (Exception error) { issues.Add(error.Message); }
        Issues = issues;
        return issues.Count == 0;
    }

    public override void AfterParentChanged() => Validate();
    public override TimeSpan GetEstimatedDuration() => TimeSpan.FromSeconds(ExposureTime) + TimeSpan.FromMinutes(MaximumWaitMinutes);
    public override object Clone() {
        var clone = new SatelliteAwareExposure(profiles, camera, imaging, saver, history) {
            ExposureTime = ExposureTime, ExposureCount = 0,
            Binning = Binning is null ? new(1, 1) : new(Binning.X, Binning.Y),
            Gain = Gain, Offset = Offset, ImageType = ImageType,
            EnginePath = EnginePath, CatalogGroup = CatalogGroup, Offline = Offline,
            MaximumWaitMinutes = MaximumWaitMinutes, LookAheadMinutes = LookAheadMinutes,
            MaxEpochAgeDays = MaxEpochAgeDays, AngularMarginDegrees = AngularMarginDegrees,
            PaddingSeconds = PaddingSeconds, HandoffGuardSeconds = HandoffGuardSeconds,
            SampleSeconds = SampleSeconds, MinimumTargetAltitude = MinimumTargetAltitude,
            MaximumSunAltitude = MaximumSunAltitude, SunlitOnly = SunlitOnly,
            FocalLengthOverrideMm = FocalLengthOverrideMm, SensorWidthOverrideMm = SensorWidthOverrideMm,
            SensorHeightOverrideMm = SensorHeightOverrideMm
        };
        clone.CopyMetaData(this);
        return clone;
    }
}
