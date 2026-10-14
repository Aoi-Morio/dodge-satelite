using System.ComponentModel.Composition;
using System.ComponentModel.Composition.Hosting;
using System.IO;
using System.Runtime.ExceptionServices;
using System.Windows;
using System.Windows.Controls;
using NINA.Sequencer.SequenceItem.Imaging;
using DodgeSatelite.Gate;
using Moq;
using NINA.Astrometry;
using NINA.Astrometry.Interfaces;
using NINA.Sequencer.Container;
using NINA.Core.Enum;
using NINA.Core.Model.Equipment;
using NINA.Core.Model;
using NINA.Equipment.Equipment.MyCamera;
using NINA.Equipment.Interfaces.Mediator;
using NINA.Plugin.Interfaces;
using NINA.Profile.Interfaces;
using NINA.Sequencer.SequenceItem;
using NINA.Sequencer.Utility;
using NINA.WPF.Base.Interfaces.Mediator;
using NINA.WPF.Base.Interfaces.ViewModel;
using Xunit;

namespace DodgeSatelite.NINA.Tests;

public class PluginTests {
    private static void Sta(Action action) {
        Exception? error = null;
        var thread = new Thread(() => { try { action(); } catch (Exception caught) { error = caught; } });
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(30)), "STA plugin test did not finish.");
        if (error is not null) ExceptionDispatchInfo.Capture(error).Throw();
    }

    private static Mock<ICameraMediator> Camera() {
        var camera = new Mock<ICameraMediator>();
        camera.Setup(c => c.GetInfo()).Returns(new CameraInfo { Connected = false, XSize = 6000, YSize = 4000, PixelSize = 3.9 });
        return camera;
    }

    private static SatelliteAwareExposure Item() => new(new Mock<IProfileService>().Object,
        Camera().Object, new Mock<IImagingMediator>().Object, new Mock<IImageSaveMediator>().Object,
        new Mock<IImageHistoryVM>().Object);

    [Fact] public void MefDiscoversManifestInstructionAndCompiledResources() => Sta(() => {
        using var catalog = new AssemblyCatalog(typeof(SatellitePlugin).Assembly);
        using var container = new CompositionContainer(catalog);
        container.ComposeExportedValue(new Mock<IProfileService>().Object);
        container.ComposeExportedValue(Camera().Object);
        container.ComposeExportedValue(new Mock<IImagingMediator>().Object);
        container.ComposeExportedValue(new Mock<IImageSaveMediator>().Object);
        container.ComposeExportedValue(new Mock<IImageHistoryVM>().Object);
        var manifest = container.GetExportedValue<IPluginManifest>();
        Assert.NotNull(manifest);
        Assert.Equal("dodge satelite", manifest.Name);
        Assert.Equal("ecb4f88d-f91a-4c0a-b7a5-a0eb028a3782", manifest.Identifier);
        Assert.IsType<SatelliteAwareExposure>(container.GetExportedValue<ISequenceItem>());
        var dictionary = container.GetExportedValue<ResourceDictionary>();
        Assert.NotNull(dictionary);
        Assert.True(dictionary.Contains(new DataTemplateKey(typeof(SatelliteAwareExposure))));
        var template = Assert.IsType<DataTemplate>(dictionary[new DataTemplateKey(typeof(SatelliteAwareExposure))]);
        Assert.IsType<StackPanel>(template.LoadContent());
    });

    [Fact] public void StandardExposureTemplateUsesTheHostImplicitDataTemplateKey() => Sta(() => {
        var host = new ContentControl();
        var expected = new DataTemplate(typeof(TakeExposure));
        host.Resources.Add(new DataTemplateKey(typeof(TakeExposure)), expected);
        var selector = new StandardExposureTemplateSelector();
        Assert.Same(expected, selector.SelectTemplate(Item(), host));
    });

    [Fact] public void ClonePreservesSettingsButNotRuntimeState() => Sta(() => {
        var item = Item();
        item.ExposureTime = 45;
        item.CatalogGroup = "starlink";
        item.Offline = true;
        item.Binning = new(2, 2);
        item.Gain = 100;
        item.MaximumWaitMinutes = 3;
        item.SensorWidthOverrideMm = 23.5;
        var copy = Assert.IsType<SatelliteAwareExposure>(item.Clone());
        Assert.Equal(45, copy.ExposureTime);
        Assert.Equal("starlink", copy.CatalogGroup);
        Assert.True(copy.Offline);
        Assert.Equal(100, copy.Gain);
        Assert.Equal(3, copy.MaximumWaitMinutes);
        Assert.Equal(23.5, copy.SensorWidthOverrideMm);
        Assert.Equal(0, copy.ExposureCount);
        Assert.NotSame(item.Binning, copy.Binning);
        Assert.Equal(InstructionErrorBehavior.AbortOnError, copy.ErrorBehavior);
    });

    [Fact] public void EngineDefaultsToPluginFolderWithoutMachineSpecificPath() {
        var item = Item();
        Assert.EndsWith(Path.Combine("Engine", "dodge-satelite-engine.exe"), item.ResolveEnginePath());
        Assert.Equal("", item.EnginePath);
    }

    [Fact] public void ContextChangesInvalidateIdentity() {
        var now = DateTimeOffset.UtcNow;
        var a = new ObservationConfig(new(35, 139, 40, "site"), new(10, 41, "target"),
            new(400, 23.5, 15.6), Protocol.Utc(now), Protocol.Utc(now.AddMinutes(5)), 30);
        var timeOnly = a with { Start = Protocol.Utc(now.AddSeconds(10)), End = Protocol.Utc(now.AddMinutes(6)) };
        Assert.Equal(SatelliteAwareExposure.ContextKey(a, "visual", false), SatelliteAwareExposure.ContextKey(timeOnly, "visual", false));
        Assert.NotEqual(SatelliteAwareExposure.ContextKey(a, "visual", false),
            SatelliteAwareExposure.ContextKey(a with { Target = new(11, 41, "target") }, "visual", false));
        Assert.NotEqual(SatelliteAwareExposure.ContextKey(a, "visual", false), SatelliteAwareExposure.ContextKey(a, "starlink", false));
    }

    [Fact] public void NinaCoordinatesAndPhysicalSensorAreConvertedWithoutBinningOrRaUnitErrors() => Sta(() => {
        var profiles = new Mock<IProfileService> { DefaultValue = DefaultValue.Mock };
        profiles.Setup(p => p.ActiveProfile.AstrometrySettings.Latitude).Returns(-33.9);
        profiles.Setup(p => p.ActiveProfile.AstrometrySettings.Longitude).Returns(151.2);
        profiles.Setup(p => p.ActiveProfile.AstrometrySettings.Elevation).Returns(42);
        profiles.Setup(p => p.ActiveProfile.CameraSettings.PixelSize).Returns(3.9);
        profiles.Setup(p => p.ActiveProfile.TelescopeSettings.FocalLength).Returns(400);
        var target = new InputTarget(Angle.ByDegree(-33.9), Angle.ByDegree(151.2), null!);
        target.DeepSkyObject = new Mock<IDeepSkyObject>().Object;
        target.InputCoordinates.Coordinates = new Coordinates(Angle.ByDegree(150), Angle.ByDegree(-20), Epoch.J2000);
        var parent = new Mock<IDeepSkyObjectContainer>();
        parent.Setup(p => p.Target).Returns(target);
        var item = new SatelliteAwareExposure(profiles.Object, Camera().Object,
            new Mock<IImagingMediator>().Object, new Mock<IImageSaveMediator>().Object,
            new Mock<IImageHistoryVM>().Object) { Binning = new(2, 2) };
        // Avoid hardware/file-path validation when attaching this test-only context.
        typeof(global::NINA.Sequencer.SequenceItem.SequenceItem).GetProperty("Parent")!.SetValue(item, parent.Object);
        var config = item.BuildObservation(DateTimeOffset.UtcNow);
        Assert.Equal(-33.9, config.Site.LatitudeDeg);
        Assert.Equal(151.2, config.Site.LongitudeDeg);
        Assert.Equal(150, config.Target.RaDeg, 8);
        Assert.Equal(-20, config.Target.DecDeg, 8);
        Assert.Equal(400, config.Equipment.FocalLengthMm);
        Assert.Equal(23.4, config.Equipment.SensorWidthMm, 8);
        Assert.Equal(15.6, config.Equipment.SensorHeightMm, 8);
        item.SensorWidthOverrideMm = 20;
        Assert.Equal(20, item.BuildObservation(DateTimeOffset.UtcNow).Equipment.SensorWidthMm);
    });
}
