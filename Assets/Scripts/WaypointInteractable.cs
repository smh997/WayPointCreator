using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.UI;
using Microsoft.MixedReality.Toolkit.Utilities;
using UnityEngine;

[RequireComponent(typeof(Waypoint))]
public class WaypointInteractable : MonoBehaviour, IMixedRealityPointerHandler, IMixedRealityTouchHandler
{
    private WaypointManager manager;
    private Waypoint waypoint;
    

    private void Awake()
    {
        manager = FindObjectOfType<WaypointManager>();
        waypoint = GetComponent<Waypoint>();
    }

    public void OnPointerClicked(MixedRealityPointerEventData eventData)
    {
        Debug.Log("Waypoint clicked: " + gameObject.name);
        if (manager.Mode == WaypointMode.Delete)
        {
            manager.RemoveWaypoint(waypoint);
        }
        eventData.Use();
    }

    public void OnPointerDown(MixedRealityPointerEventData eventData) { }
    public void OnPointerDragged(MixedRealityPointerEventData eventData) { }
    public void OnPointerUp(MixedRealityPointerEventData eventData) { }

    void IMixedRealityTouchHandler.OnTouchStarted(HandTrackingInputEventData eventData)
    {
        Debug.Log("Waypoint touched: " + gameObject.name);
        if (manager.Mode == WaypointMode.Delete)
        {
            manager.RemoveWaypoint(waypoint);
        }
        else if (manager.Mode == WaypointMode.Edit)
        {
            manager.StartEdit(waypoint);
        }
        eventData.Use();
    }

    void IMixedRealityTouchHandler.OnTouchCompleted(HandTrackingInputEventData eventData) { }

    void IMixedRealityTouchHandler.OnTouchUpdated(HandTrackingInputEventData eventData) { }
}
