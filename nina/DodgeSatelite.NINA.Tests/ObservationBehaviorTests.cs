using System.IO;
using System.Reflection;
using System.Runtime.ExceptionServices;
using System.Text.Json;
using DodgeSatelite.Gate;
using Moq;
using Newtonsoft.Json;
using NINA.Astrometry;
using NINA.Astrometry.Interfaces;
using NINA.Core.Model;
using NINA.Core.Model.Equipment;
using NINA.Equipment.Equipment.MyCamera;
using NINA.Equipment.Interfaces.Mediator;
using NINA.Equipment.Model;
using NINA.Image.Interfaces;
using NINA.Profile.Interfaces;
using NINA.Sequencer;
using NINA.Sequencer.Container;
using NINA.Sequencer.SequenceItem;
using NINA.Sequencer.Serialization;
using NINA.Sequencer.Utility.DateTimeProvider;
using NINA.WPF.Base.Interfaces.Mediator;
using NINA.WPF.Base.Interfaces.ViewModel;
using Xunit;

namespace DodgeSatelite.NINA.Tests;

public class ObservationBehaviorTests {
    private static void Sta(Func<Task> action) {
        Exception? error = null;
        var thread = new Thread(() => { try { action().GetAwaiter().GetResult(); } catch (Exception e) { error = e; } });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(30)), "Behavior test timed out.");
        if (error is not null) ExceptionDispatchInfo.Capture(error).Throw();
    }

    private sealed class CaptureReached : Exception { }

    private sealed class Fixture : IDisposable {
        public readonly string DirectoryPath = Path.Combine(Path.GetTempPath(), "dodge-test-" + Guid.NewGuid().ToString("N"));
        public readonly Mock<IProfileService> Profiles = new() { DefaultValue = DefaultValue.Mock };
        public readonly Mock<ICameraMediator> Camera = new();
        public readonly Mock<IImagingMediator> Imaging = new();
        public readonly Mock<IImageSaveMediator> Saver = new();
        public readonly Mock<IImageHistoryVM> History = new();
        public readonly SatelliteAwareExposure Item;
        public readonly InputTarget Target;
        public readonly Mock<IDeepSkyObjectContainer> Parent = new();

        public Fixture() {
            Directory.CreateDirectory(DirectoryPath);
            var placeholder = Path.Combine(DirectoryPath, "never-executed-engine.exe");
            File.WriteAllText(placeholder, "Test placeholder. Prediction client is injected; no executable runs.");
            Profiles.Setup(p => p.ActiveProfile.ImageFileSettings.FilePath).Returns(DirectoryPath);
            Profiles.Setup(p => p.ActiveProfile.AstrometrySettings.Latitude).Returns(35);
            Profiles.Setup(p => p.ActiveProfile.AstrometrySettings.Longitude).Returns(139);
            Profiles.Setup(p => p.ActiveProfile.AstrometrySettings.Elevation).Returns(40);
            Profiles.Setup(p => p.ActiveProfile.CameraSettings.PixelSize).Returns(3.9);
            Profiles.Setup(p => p.ActiveProfile.TelescopeSettings.FocalLength).Returns(400);
            Camera.Setup(c => c.GetInfo()).Returns(new CameraInfo {
                Connected = true, XSize = 6000, YSize = 4000, PixelSize = 3.9
            });
            // If capture is reached, stop at the boundary of NINA's standard
            // pipeline. No real camera, image processing or file saving occurs.
            Imaging.Setup(i => i.CaptureImage(It.IsAny<CaptureSequence>(), It.IsAny<CancellationToken>(),
                It.IsAny<IProgress<ApplicationStatus>>(), It.IsAny<string>())).ThrowsAsync(new CaptureReached());
            Item = NewItem();
            Item.EnginePath = placeholder;
            Item.ExposureTime = 10;
            Item.HandoffGuardSeconds = 1;
            Item.MaximumWaitMinutes = 0.01;
            Target = new InputTarget(Angle.ByDegree(35), Angle.ByDegree(139), null!);
            Target.DeepSkyObject = new Mock<IDeepSkyObject>().Object;
            Target.InputCoordinates.Coordinates = new Coordinates(Angle.ByDegree(150), Angle.ByDegree(30), Epoch.J2000);
            Parent.Setup(p => p.Target).Returns(Target);
            Item.AttachNewParent(Parent.Object);
            Assert.True(Item.Validate(), string.Join("; ", Item.Issues));
        }

        public SatelliteAwareExposure NewItem() => new(Profiles.Object, Camera.Object, Imaging.Object, Saver.Object, History.Object);

        public void InstallClient(Func<ForecastRequest, CancellationToken, Task<Forecast>> query) {
            var client = new Mock<IEngineClient>();
            client.Setup(c => c.QueryAsync(It.IsAny<ForecastRequest>(), It.IsAny<CancellationToken>()))
                .Returns(query);
            typeof(SatelliteAwareExposure).GetField("gate", BindingFlags.Instance | BindingFlags.NonPublic)!
                .SetValue(Item, new ExposureGate(client.Object));
            typeof(SatelliteAwareExposure).GetField("gateExecutable", BindingFlags.Instance | BindingFlags.NonPublic)!
                .SetValue(Item, Item.ResolveEnginePath());
        }

        public void VerifyNoCapture() {
            Assert.Empty(Imaging.Invocations);
            Assert.Empty(Saver.Invocations);
            Assert.Empty(History.Invocations);
        }

        public void Dispose() => Directory.Delete(DirectoryPath, recursive: true);
    }

    private static Forecast ForecastFor(ForecastRequest request, bool open) {
        var start = Protocol.ParseUtc(request.Config.Start);
        var response = new ForecastResponse(1, request.RequestId, "ok", null,
            Protocol.Utc(DateTimeOffset.UtcNow), request.Config.Start, request.Config.End,
            open ? [new(Protocol.Utc(start.AddSeconds(1)), request.Config.End)] : [],
            1, new string('a', 64), []);
        return Protocol.Validate(System.Text.Json.JsonSerializer.Serialize(response, Protocol.Json), request, DateTimeOffset.UtcNow);
    }

    [Theory]
    [InlineData("stale")][InlineData("protocol")][InlineData("engine")]
    public void PredictionFailureNeverCallsCaptureOrSave(string kind) => Sta(async () => {
        using var f = new Fixture();
        f.InstallClient((_, _) => Task.FromException<Forecast>(kind switch {
            "stale" => new InvalidOperationException("Orbital elements exceed the configured epoch limit"),
            "protocol" => new InvalidDataException("Engine protocol/request identifier mismatch"),
            _ => new IOException("Engine unavailable")
        }));
        await Assert.ThrowsAnyAsync<Exception>(() => f.Item.Execute(null!, default));
        f.VerifyNoCapture();
    });

    [Fact] public void NoWindowTimesOutWithoutCapture() => Sta(async () => {
        using var f = new Fixture();
        f.InstallClient((request, _) => Task.FromResult(ForecastFor(request, false)));
        await Assert.ThrowsAsync<TimeoutException>(() => f.Item.Execute(null!, default));
        f.VerifyNoCapture();
    });

    [Fact] public void CancellationDuringPredictionDoesNotCapture() => Sta(async () => {
        using var f = new Fixture();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        f.InstallClient(async (_, token) => {
            entered.SetResult();
            await Task.Delay(Timeout.Infinite, token);
            throw new Exception("unreachable");
        });
        using var cancel = new CancellationTokenSource();
        var executing = f.Item.Execute(null!, cancel.Token);
        await entered.Task;
        cancel.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => executing);
        f.VerifyNoCapture();
    });

    [Theory]
    [InlineData("DARK")][InlineData("FLAT")]
    public void LightChangedToCalibrationWhileWaitingDoesNotCapture(string imageType) => Sta(async () => {
        using var f = new Fixture();
        f.Item.MaximumWaitMinutes = 0.1;
        f.InstallClient((request, _) => {
            f.Item.ImageType = imageType;
            return Task.FromResult(ForecastFor(request, true));
        });
        await Assert.ThrowsAsync<InvalidOperationException>(() => f.Item.Execute(null!, default));
        f.VerifyNoCapture();
    });

    [Fact] public void EnginePathChangedWhileWaitingRequiresRestartWithoutCapture() => Sta(async () => {
        using var f = new Fixture();
        f.Item.MaximumWaitMinutes = 0.1;
        var replacement = Path.Combine(f.DirectoryPath, "other-never-executed.exe");
        File.WriteAllText(replacement, "Another test placeholder, never executed.");
        f.InstallClient((request, _) => {
            f.Item.EnginePath = replacement;
            return Task.FromResult(ForecastFor(request, true));
        });
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => f.Item.Execute(null!, default));
        Assert.Contains("engine path changed", error.Message);
        f.VerifyNoCapture();
    });

    [Fact] public void TargetChangedDuringPredictionIsRecomputedBeforeCapture() => Sta(async () => {
        using var f = new Fixture();
        f.Item.MaximumWaitMinutes = 0.2;
        var calls = 0;
        f.InstallClient((request, _) => {
            calls++;
            if (calls == 1) {
                Assert.Equal(150, request.Config.Target.RaDeg, 6);
                f.Target.InputCoordinates.Coordinates = new Coordinates(Angle.ByDegree(151), Angle.ByDegree(30), Epoch.J2000);
            } else {
                Assert.Equal(151, request.Config.Target.RaDeg, 6);
            }
            return Task.FromResult(ForecastFor(request, true));
        });
        await Assert.ThrowsAsync<CaptureReached>(() => f.Item.Execute(null!, default));
        Assert.Equal(2, calls);
        Assert.Single(f.Imaging.Invocations);
    });

    [Fact] public void SameInstructionCanRunAgainAfterCancellation() => Sta(async () => {
        using var f = new Fixture();
        f.Item.MaximumWaitMinutes = 0.1;
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var calls = 0;
        f.InstallClient(async (request, token) => {
            if (++calls == 1) {
                entered.SetResult();
                await Task.Delay(Timeout.Infinite, token);
            }
            return ForecastFor(request, true);
        });
        using var cancel = new CancellationTokenSource();
        var first = f.Item.Execute(null!, cancel.Token);
        await entered.Task;
        cancel.Cancel();
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => first);
        f.VerifyNoCapture();
        await Assert.ThrowsAsync<CaptureReached>(() => f.Item.Execute(null!, default));
        Assert.Equal(2, calls);
        Assert.Single(f.Imaging.Invocations);
    });

    [Fact] public void OpenWindowDelegatesExactlyOnceWithNinaExposureSettings() => Sta(async () => {
        using var f = new Fixture();
        f.Item.MaximumWaitMinutes = 0.1;
        f.Item.Gain = 101;
        f.Item.Offset = 7;
        f.Item.Binning = new(2, 2);
        f.InstallClient((request, _) => Task.FromResult(ForecastFor(request, true)));
        await Assert.ThrowsAsync<CaptureReached>(() => f.Item.Execute(null!, default));
        var invocation = Assert.Single(f.Imaging.Invocations);
        var capture = Assert.IsType<CaptureSequence>(invocation.Arguments[0]);
        Assert.Equal("LIGHT", capture.ImageType);
        Assert.Equal(10, capture.ExposureTime);
        Assert.Equal(101, capture.Gain);
        Assert.Equal(7, capture.Offset);
        Assert.Equal(2, capture.Binning.X);
        Assert.Empty(f.Saver.Invocations);
    });

    [Fact] public void RealNinaSequenceSerializerRestoresPluginAndSettings() => Sta(() => {
        using var f = new Fixture();
        f.Item.CatalogGroup = "starlink";
        f.Item.Offline = true;
        f.Item.Gain = 87;
        f.Item.Offset = 13;
        f.Item.Binning = new(2, 3);
        f.Item.MaxEpochAgeDays = 4;
        f.Item.SensorWidthOverrideMm = 20;
        f.Item.SensorHeightOverrideMm = 12;
        f.Item.MaximumWaitMinutes = 6;
        var sequence = new SequentialContainer();
        typeof(global::NINA.Sequencer.SequenceItem.SequenceItem).GetProperty("Parent")!.SetValue(f.Item, sequence);
        sequence.Items.Add(f.Item);
        var factory = new Mock<ISequencerFactory>();
        factory.SetupGet(s => s.DateTimeProviders).Returns(new List<IDateTimeProvider>());
        factory.Setup(s => s.GetContainer<SequentialContainer>()).Returns(() => new SequentialContainer());
        factory.Setup(s => s.GetItem<SatelliteAwareExposure>()).Returns(f.NewItem);
        var converter = new SequenceJsonConverter(factory.Object);
        var json = converter.Serialize(sequence);
        Assert.DoesNotContain("cachedContext", json);
        Assert.DoesNotContain("StatusText", json);
        var restored = converter.Deserialize(json);
        var copy = Assert.IsType<SatelliteAwareExposure>(Assert.Single(restored.Items));
        Assert.Equal("starlink", copy.CatalogGroup);
        Assert.True(copy.Offline);
        Assert.Equal(87, copy.Gain);
        Assert.Equal(13, copy.Offset);
        Assert.Equal(2, copy.Binning.X);
        Assert.Equal(3, copy.Binning.Y);
        Assert.Equal(4, copy.MaxEpochAgeDays);
        Assert.Equal(20, copy.SensorWidthOverrideMm);
        Assert.Equal(12, copy.SensorHeightOverrideMm);
        Assert.Equal(6, copy.MaximumWaitMinutes);
        Assert.Same(restored, copy.Parent);
        return Task.CompletedTask;
    });
}
