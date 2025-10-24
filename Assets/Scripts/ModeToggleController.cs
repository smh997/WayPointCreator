using Microsoft.MixedReality.Toolkit.UI;
using TMPro;
using UnityEngine;

public class ModeToggleController : MonoBehaviour
{
    [Header("References")]
    public WaypointManager waypointManager;
    public PressableButtonHoloLens2 toggleButton;
    public TextMeshPro labelText;

    private bool deleteMode = false;

    private void Start()
    {
        // Initialize label
        UpdateLabel();

        // Add listener to the button
        toggleButton.ButtonPressed.AddListener(ToggleMode);
    }

    private void ToggleMode()
    {
        // Switch mode
        deleteMode = !deleteMode;

        // Update visuals
        UpdateLabel();

        // Notify WaypointManager
        waypointManager.SetDeleteMode(deleteMode);
    }

    private void UpdateLabel()
    {
        if (deleteMode)
        {
            labelText.text = "Delete Mode";
            labelText.color = Color.red;
        }
        else
        {
            labelText.text = "Create Mode";
            labelText.color = Color.green;
        }
    }
}
