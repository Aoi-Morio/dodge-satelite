using System.Diagnostics;
using System.Text;
using System.Text.Json;

namespace DodgeSatelite.Gate;

public interface IEngineClient {
    Task<Forecast> QueryAsync(ForecastRequest request, CancellationToken token);
}

public sealed class EngineClient(string executable, TimeSpan? timeout = null,
    IReadOnlyList<string>? prefixArguments = null) : IEngineClient {
    private static async Task<string> ReadLimitedAsync(StreamReader reader, int limit, CancellationToken token) {
        var result = new StringBuilder();
        var buffer = new char[4096];
        while (true) {
            var count = await reader.ReadAsync(buffer.AsMemory(), token).ConfigureAwait(false);
            if (count == 0) return result.ToString();
            if (result.Length + count > limit) throw new InvalidDataException("Engine output exceeded its size limit.");
            result.Append(buffer, 0, count);
        }
    }

    private static void Kill(Process process) {
        try { if (!process.HasExited) process.Kill(entireProcessTree: true); }
        catch (InvalidOperationException) { }
        catch (System.ComponentModel.Win32Exception) { }
    }

    public async Task<Forecast> QueryAsync(ForecastRequest request, CancellationToken token) {
        token.ThrowIfCancellationRequested();
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(token);
        deadline.CancelAfter(timeout ?? TimeSpan.FromMinutes(2));
        var info = new ProcessStartInfo(Path.GetFullPath(executable)) {
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
            WorkingDirectory = Path.GetDirectoryName(Path.GetFullPath(executable))!
        };
        if (prefixArguments is not null) foreach (var argument in prefixArguments) info.ArgumentList.Add(argument);
        info.ArgumentList.Add("nina-bridge");
        using var process = new Process { StartInfo = info };
        process.Start();
        using var cancellation = deadline.Token.Register(() => Kill(process));
        var stdout = ReadLimitedAsync(process.StandardOutput, 2 * 1024 * 1024, deadline.Token);
        var stderr = ReadLimitedAsync(process.StandardError, 64 * 1024, deadline.Token);
        try {
            var data = JsonSerializer.Serialize(request, Protocol.Json);
            if (Encoding.UTF8.GetByteCount(data) > 65536) throw new InvalidDataException("Prediction request exceeds 64 KiB.");
            await process.StandardInput.WriteAsync(data.AsMemory(), deadline.Token).ConfigureAwait(false);
            process.StandardInput.Close();
            await process.WaitForExitAsync(deadline.Token).ConfigureAwait(false);
            await Task.WhenAll(stdout, stderr).ConfigureAwait(false);
            token.ThrowIfCancellationRequested();
            if (process.ExitCode != 0) {
                try { Protocol.Validate(await stdout.ConfigureAwait(false), request, DateTimeOffset.UtcNow); }
                catch (InvalidOperationException) { throw; }
                catch (Exception) { /* Report the bounded stderr if no protocol error is available. */ }
                throw new InvalidOperationException($"Prediction engine failed ({process.ExitCode}). {await stderr.ConfigureAwait(false)}");
            }
            return Protocol.Validate(await stdout.ConfigureAwait(false), request, DateTimeOffset.UtcNow);
        } catch (Exception) when (token.IsCancellationRequested) {
            throw new OperationCanceledException(token);
        } catch (Exception) when (deadline.IsCancellationRequested) {
            throw new TimeoutException("Satellite prediction exceeded its time limit. No exposure started.");
        } finally {
            Kill(process);
        }
    }
}
