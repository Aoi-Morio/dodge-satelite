using System.Diagnostics;

namespace DodgeSatelite.Gate;

public sealed class ExposureGate(IEngineClient client) {
    private Forecast? cached;
    private string? cachedContext;
    private DateTimeOffset lastWall;
    private long lastMonotonic;

    public void Invalidate() { cached = null; cachedContext = null; }

    public bool CanStart(string contextKey, double exposureSeconds, double guardSeconds) {
        var now = DateTimeOffset.UtcNow;
        var tick = Stopwatch.GetTimestamp();
        if (lastMonotonic != 0 && Math.Abs((now - lastWall - Stopwatch.GetElapsedTime(lastMonotonic, tick)).TotalSeconds) > 2) {
            Invalidate();
        }
        return cached is not null && cachedContext == contextKey &&
            now - cached.GeneratedAt <= TimeSpan.FromMinutes(2) &&
            Protocol.NextStart(cached, now, exposureSeconds, guardSeconds) is DateTimeOffset start && start <= now;
    }

    public async Task<ForecastResponse> WaitAsync(string contextKey, Func<ForecastRequest> requestFactory,
        double exposureSeconds, double guardSeconds, TimeSpan maximumWait,
        Action<string>? progress, CancellationToken token) {
        var timer = Stopwatch.StartNew();
        while (timer.Elapsed <= maximumWait) {
            token.ThrowIfCancellationRequested();
            var now = DateTimeOffset.UtcNow;
            var tick = Stopwatch.GetTimestamp();
            if (lastMonotonic != 0 && Math.Abs((now - lastWall - Stopwatch.GetElapsedTime(lastMonotonic, tick)).TotalSeconds) > 2) {
                Invalidate();
            }
            lastWall = now;
            lastMonotonic = tick;
            if (cachedContext != contextKey || cached is null || now >= cached.Session.End ||
                now - cached.GeneratedAt > TimeSpan.FromMinutes(2)) {
                progress?.Invoke("dodge satelite: calculating satellite crossings / 衛星通過を計算中");
                using var queryDeadline = CancellationTokenSource.CreateLinkedTokenSource(token);
                var queryRemaining = maximumWait - timer.Elapsed;
                if (queryRemaining <= TimeSpan.Zero) break;
                queryDeadline.CancelAfter(queryRemaining);
                try {
                    cached = await client.QueryAsync(requestFactory(), queryDeadline.Token).ConfigureAwait(false);
                } catch (OperationCanceledException) when (!token.IsCancellationRequested && queryDeadline.IsCancellationRequested) {
                    throw new TimeoutException("Prediction exceeded the maximum waiting time. No exposure started.");
                }
                cachedContext = contextKey;
                now = DateTimeOffset.UtcNow;
                if (timer.Elapsed > maximumWait) break;
                if (now - cached.GeneratedAt > TimeSpan.FromMinutes(2)) { Invalidate(); continue; }
            }
            var next = Protocol.NextStart(cached, now, exposureSeconds, guardSeconds);
            if (next is null) {
                // Do not spin/re-download while the same no-window forecast is current.
                progress?.Invoke("dodge satelite: no predicted window yet / 条件を満たす露光枠を待機中");
            } else if (next.Value <= now) {
                return cached.Response;
            } else {
                progress?.Invoke($"dodge satelite: waiting until {next.Value:HH:mm:ss} UTC / 衛星リスク区間を待機中");
            }
            var remaining = maximumWait - timer.Elapsed;
            if (remaining <= TimeSpan.Zero) break;
            var delay = next is null ? TimeSpan.FromSeconds(5) : next.Value - now;
            if (delay > TimeSpan.FromSeconds(1)) delay = TimeSpan.FromSeconds(1);
            if (delay > remaining) delay = remaining;
            await Task.Delay(delay, token).ConfigureAwait(false);
        }
        throw new TimeoutException("No predicted exposure window within the maximum waiting time. No exposure started.");
    }
}
