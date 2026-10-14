using System.ComponentModel.Composition;
using System.Windows;

namespace DodgeSatelite.NINA;

[Export(typeof(ResourceDictionary))]
public partial class InstructionTemplates : ResourceDictionary {
    public InstructionTemplates() => InitializeComponent();
}
