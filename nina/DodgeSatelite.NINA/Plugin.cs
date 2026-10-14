using System.ComponentModel.Composition;
using System.Reflection;
using System.Runtime.InteropServices;
using NINA.Plugin;
using NINA.Plugin.Interfaces;

[assembly: Guid("ecb4f88d-f91a-4c0a-b7a5-a0eb028a3782")]
[assembly: ComVisible(false)]
[assembly: AssemblyMetadata("MinimumApplicationVersion", "3.2.0.9001")]
[assembly: AssemblyMetadata("License", "MIT")]
[assembly: AssemblyMetadata("LicenseURL", "https://github.com/Aoi-Morio/dodge-satelite/blob/main/LICENSE")]
[assembly: AssemblyMetadata("Repository", "https://github.com/Aoi-Morio/dodge-satelite")]
[assembly: AssemblyMetadata("Homepage", "https://github.com/Aoi-Morio/dodge-satelite/tree/main/nina")]
[assembly: AssemblyMetadata("ChangelogURL", "https://github.com/Aoi-Morio/dodge-satelite/blob/main/nina/CHANGELOG.md")]
[assembly: AssemblyMetadata("Tags", "Satellite,Imaging,Sequencer,Astrophotography")]
[assembly: AssemblyMetadata("LongDescription", "Waits for a catalog-predicted window before a standard NINA light exposure. Uses the active target, site and camera/telescope profile. Experimental: no guarantee of clean frames or measured accuracy. Prediction failure/stale data stops this instruction by default.")]

namespace DodgeSatelite.NINA;

[Export(typeof(IPluginManifest))]
public sealed class SatellitePlugin : PluginBase { }
