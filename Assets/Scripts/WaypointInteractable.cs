using Microsoft.MixedReality.Toolkit.Input;
using UnityEngine;

[RequireComponent(typeof(Waypoint))]
public class WaypointInteractable : MonoBehaviour, IMixedRealityPointerHandler, IMixedRealityTouchHandler
{
    private Waypoint waypoint;

    private WaypointManager manager;

    private void Awake()
    {
        waypoint = GetComponent<Waypoint>();
        manager = FindObjectOfType<WaypointManager>();
        Debug.Log($"SMHLOG: {manager.DeleteMode}");
    }

    public void OnPointerClicked(MixedRealityPointerEventData eventData)
    {
        Debug.Log("SMHLOG!!!");
        Debug.Log("Waypoint clicked: " + gameObject.name);
        if (manager.DeleteMode)
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
        Debug.Log("Yes! SMHLOG!!!");
        Debug.Log("Waypoint touched: " + gameObject.name);
        if (manager.DeleteMode)
        {
            manager.RemoveWaypoint(waypoint);
        }
        eventData.Use();
    }

    void IMixedRealityTouchHandler.OnTouchCompleted(HandTrackingInputEventData eventData) { }

    void IMixedRealityTouchHandler.OnTouchUpdated(HandTrackingInputEventData eventData) { }
}
