using System.Text.Json;
using DodgeSatelite.Gate;
using Xunit;

namespace DodgeSatelite.Gate.Tests;

public class GateTests {
    private static ForecastRequest Request(DateTimeOffset now) => new(1, "unique-id",
        new(new(35, 139, 40, "test"), new(10, 41, "target"), new(400, 23.5, 15.6),
            Protocol.Utc(now.AddSeconds(-5)), Protocol.Utc(now.AddMinutes(5)), 30));

    private static ForecastResponse Response(ForecastRequest request, DateTimeOffset now,
        ForecastWindow[]? windows = null) => new(1, request.RequestId, "ok", null,
            Protocol.Utc(now), request.Config.Start, request.Config.End,
            windows ?? [new(Protocol.Utc(now.AddSeconds(-4)), request.Config.End)],
            12, new string('a', 64), ["Catalog limited; no accuracy claim."]);

    private static string Encode(ForecastResponse response) => JsonSerializer.Serialize(response, Protocol.Json);

    [Fact] public void FullExposureAndGuardMustFit() {
        var now = new DateTimeOffset(2026, 10, 14, 21, 0, 0, TimeSpan.Zero);
        var request = Request(now);
        var response = Response(request, now, [new(Protocol.Utc(now.AddSeconds(-4)), Protocol.Utc(now.AddSeconds(32)))]);
        var forecast = Protocol.Validate(Encode(response), request, now);
        Assert.Null(Protocol.NextStart(forecast, now, 30, 3));
        Assert.Equal(now, Protocol.NextStart(forecast, now, 29, 3));
    }

    [Fact] public void FutureWindowGetsLeadingGuard() {
        var now = new DateTimeOffset(2026, 10, 14, 21, 0, 0, TimeSpan.Zero);
        var request = Request(now);
        var response = Response(request, now, [new(Protocol.Utc(now.AddSeconds(10)), request.Config.End)]);
        var forecast = Protocol.Validate(Encode(response), request, now);
        Assert.Equal(now.AddSeconds(13), Protocol.NextStart(forecast, now, 30, 3));
    }

    [Theory]
    [InlineData("request")][InlineData("schema")][InlineData("epoch")][InlineData("hash")]
    [InlineData("count")][InlineData("session")][InlineData("expired")][InlineData("future")]
    public void InvalidForecastNeverAuthorizesExposure(string defect) {
        var now = DateTimeOffset.UtcNow;
        var request = Request(now);
        var response = Response(request, now);
        response = defect switch {
            "request" => response with { RequestId = "old-request" },
            "schema" => response with { SchemaVersion = 2 },
            "epoch" => response with { GeneratedAtUtc = Protocol.Utc(now.AddMinutes(-3)) },
            "hash" => response with { CatalogSha256 = "invalid" },
            "count" => response with { SatelliteCount = 0 },
            "session" => response with { SessionStartUtc = Protocol.Utc(now.AddSeconds(-3)) },
            "expired" => response with { ValidUntilUtc = Protocol.Utc(now.AddSeconds(-1)) },
            "future" => response with { GeneratedAtUtc = Protocol.Utc(now.AddMinutes(1)) },
            _ => throw new Exception()
        };
        Assert.Throws<InvalidDataException>(() => Protocol.Validate(Encode(response), request, now));
    }

    [Fact] public void EngineErrorIsActionable() {
        var now = DateTimeOffset.UtcNow;
        var request = Request(now);
        var response = Response(request, now) with { Status = "error", Error = "Refresh stale catalog" };
        var error = Assert.Throws<InvalidOperationException>(() => Protocol.Validate(Encode(response), request, now));
        Assert.Contains("Refresh", error.Message);
    }

    [Theory]
    [InlineData("2026-10-14T21:00:00")][InlineData("2026-10-14T21:00:00+09:00")][InlineData("")]
    public void TimestampMustBeExplicitUtc(string value) => Assert.Throws<InvalidDataException>(() => Protocol.ParseUtc(value));

    [Fact] public void OverlappingOrOutOfSessionWindowsAreRejected() {
        var now = DateTimeOffset.UtcNow;
        var request = Request(now);
        var response = Response(request, now, [
            new(Protocol.Utc(now), Protocol.Utc(now.AddSeconds(20))),
            new(Protocol.Utc(now.AddSeconds(10)), request.Config.End)
        ]);
        Assert.Throws<InvalidDataException>(() => Protocol.Validate(Encode(response), request, now));
    }

    private sealed class FakeClient(Func<ForecastRequest, Forecast> produce) : IEngineClient {
        public int Calls;
        public Task<Forecast> QueryAsync(ForecastRequest request, CancellationToken token) {
            Calls++;
            token.ThrowIfCancellationRequested();
            return Task.FromResult(produce(request));
        }
    }

    [Fact] public async Task GateReusesOnlyMatchingContext() {
        var client = new FakeClient(request => Protocol.Validate(Encode(Response(request, DateTimeOffset.UtcNow)), request, DateTimeOffset.UtcNow));
        var gate = new ExposureGate(client);
        await gate.WaitAsync("A", () => Request(DateTimeOffset.UtcNow), 30, 1, TimeSpan.FromSeconds(5), null, default);
        Assert.True(gate.CanStart("A", 30, 1));
        Assert.False(gate.CanStart("B", 30, 1));
        await gate.WaitAsync("A", () => Request(DateTimeOffset.UtcNow), 30, 1, TimeSpan.FromSeconds(5), null, default);
        Assert.Equal(1, client.Calls);
        await gate.WaitAsync("B", () => Request(DateTimeOffset.UtcNow), 30, 1, TimeSpan.FromSeconds(5), null, default);
        Assert.Equal(2, client.Calls);
        gate.Invalidate();
        Assert.False(gate.CanStart("B", 30, 1));
    }

    [Fact] public async Task EmptyForecastWaitsWithoutSpinningAndTimesOut() {
        var client = new FakeClient(request => Protocol.Validate(Encode(Response(request, DateTimeOffset.UtcNow, [])), request, DateTimeOffset.UtcNow));
        var gate = new ExposureGate(client);
        await Assert.ThrowsAsync<TimeoutException>(() => gate.WaitAsync("A", () => Request(DateTimeOffset.UtcNow),
            30, 1, TimeSpan.FromMilliseconds(50), null, default));
        Assert.Equal(1, client.Calls);
        Assert.False(gate.CanStart("A", 30, 1));
    }

    [Fact] public async Task CancellationStopsWaiting() {
        var client = new FakeClient(request => Protocol.Validate(Encode(Response(request, DateTimeOffset.UtcNow, [])), request, DateTimeOffset.UtcNow));
        var gate = new ExposureGate(client);
        using var token = new CancellationTokenSource(TimeSpan.FromMilliseconds(50));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => gate.WaitAsync("A", () => Request(DateTimeOffset.UtcNow),
            30, 1, TimeSpan.FromMinutes(1), null, token.Token));
    }

    [Fact] public async Task EngineProcessCancellationKillsChild() {
        var python = Environment.GetEnvironmentVariable("DODGE_SATELITE_TEST_PYTHON")
            ?? throw new InvalidOperationException("Set DODGE_SATELITE_TEST_PYTHON to run process integration tests.");
        var client = new EngineClient(python, TimeSpan.FromSeconds(10), ["-c", "import time;time.sleep(30)"]);
        using var token = new CancellationTokenSource(TimeSpan.FromMilliseconds(200));
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => client.QueryAsync(Request(DateTimeOffset.UtcNow), token.Token));
    }

    [Fact] public async Task EngineProcessTimeoutFailsClosed() {
        var python = Environment.GetEnvironmentVariable("DODGE_SATELITE_TEST_PYTHON")
            ?? throw new InvalidOperationException("Set DODGE_SATELITE_TEST_PYTHON to run process integration tests.");
        var client = new EngineClient(python, TimeSpan.FromMilliseconds(200), ["-c", "import time;time.sleep(30)"]);
        await Assert.ThrowsAsync<TimeoutException>(() => client.QueryAsync(Request(DateTimeOffset.UtcNow), default));
    }

    [Fact] public async Task RealPythonBridgeRoundTripPreservesSessionAtDotnetTickPrecision() {
        var python = Environment.GetEnvironmentVariable("DODGE_SATELITE_TEST_PYTHON")
            ?? throw new InvalidOperationException("Set DODGE_SATELITE_TEST_PYTHON to run process integration tests.");
        // Supply an in-memory synthetic catalog, with today's epoch: no network,
        // but the actual Python prediction, JSON and C# validation all execute.
        var script = """
from datetime import UTC, datetime
from importlib.resources import files
from dodge_satelite import nina_bridge
from dodge_satelite.catalog import parse_csv
text = files('dodge_satelite').joinpath('data/demo.csv').read_text()
text = text.replace('2024-05-06T19:53:04.999776', datetime.now(UTC).replace(tzinfo=None).isoformat())
nina_bridge.fetch_catalog = lambda *a, **kw: parse_csv(text, 'synthetic integration test')
raise SystemExit(nina_bridge.main())
""";
        var client = new EngineClient(python, TimeSpan.FromSeconds(60), ["-c", script]);
        var now = new DateTimeOffset(DateTimeOffset.UtcNow.Ticks / 10 * 10 + 7, TimeSpan.Zero);
        var request = Request(now);
        var result = await client.QueryAsync(request, default);
        Assert.Equal(Protocol.ParseUtc(request.Config.Start), result.Session.Start);
        Assert.Equal(Protocol.ParseUtc(request.Config.End), result.Session.End);
        Assert.Equal(1, result.Response.SatelliteCount);
    }

    [Fact] public async Task MaximumWaitAlsoCancelsAnInProgressEngineQuery() {
        var python = Environment.GetEnvironmentVariable("DODGE_SATELITE_TEST_PYTHON")
            ?? throw new InvalidOperationException("Set DODGE_SATELITE_TEST_PYTHON to run process integration tests.");
        var client = new EngineClient(python, TimeSpan.FromSeconds(30), ["-c", "import time;time.sleep(30)"]);
        var gate = new ExposureGate(client);
        var elapsed = System.Diagnostics.Stopwatch.StartNew();
        await Assert.ThrowsAsync<TimeoutException>(() => gate.WaitAsync("A", () => Request(DateTimeOffset.UtcNow),
            30, 1, TimeSpan.FromMilliseconds(200), null, default));
        Assert.True(elapsed.Elapsed < TimeSpan.FromSeconds(10));
        Assert.False(gate.CanStart("A", 30, 1));
    }
}
