using System.Windows;
using System.Windows.Controls;
using NINA.Sequencer.SequenceItem.Imaging;

namespace DodgeSatelite.NINA;

public sealed class StandardExposureTemplateSelector : DataTemplateSelector {
    public override DataTemplate SelectTemplate(object item, DependencyObject container) {
        // Implicit DataTemplates use DataTemplateKey, not the System.Type key.
        // Explicitly select the host's base template to avoid subclass recursion.
        return (DataTemplate)((FrameworkElement)container).FindResource(new DataTemplateKey(typeof(TakeExposure)));
    }
}
