using Microsoft.MixedReality.Toolkit.UI;
using TMPro;
using UnityEngine;

public class ModeToggleController : MonoBehaviour
{
    [Header("References")]
    public WaypointManager waypointManager;
    public PressableButtonHoloLens2 toggleButton;
    public PressableButtonHoloLens2 deleteAllButton;
    public TextMeshPro labelText;

    private void Start()
    {
        // Initialize label and hook up listener
        UpdateLabel();
        toggleButton.ButtonPressed.AddListener(CycleMode);
    }

    private void CycleMode()
    {
        // Cycle through Create → Edit → Delete → back to Create
        WaypointMode nextMode = waypointManager.Mode switch
        {
            WaypointMode.Create => WaypointMode.Edit,
            WaypointMode.Edit => WaypointMode.Delete,
            WaypointMode.Delete => WaypointMode.Create,
            _ => WaypointMode.Create
        };

        waypointManager.SetMode(nextMode);
        UpdateLabel();
    }

    private void UpdateLabel()
    {
        switch (waypointManager.Mode)
        {
            case WaypointMode.Create:
                labelText.text = "Create Mode";
                labelText.color = Color.green;
                deleteAllButton.gameObject.SetActive(false);
                break;

            case WaypointMode.Edit:
                labelText.text = "Edit Mode";
                labelText.color = Color.yellow;
                deleteAllButton.gameObject.SetActive(false);
                break;

            case WaypointMode.Delete:
                labelText.text = "Delete Mode";
                labelText.color = Color.red;
                deleteAllButton.gameObject.SetActive(true);
                break;
        }
    }


}
