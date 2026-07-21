using System.Collections.Generic;
using UnityEngine;
using TMPro;
using UnityEngine.UI;
using Microsoft.MixedReality.Toolkit.UI;

public enum WaypointMode
{
    Create,
    Edit,
    Delete,
    Idle
}

public enum ReferenceResolution
{
    Resolved,
    Missing,
    OutOfRange
}

public enum OffsetResult
{
    Applied,
    UnsupportedAxis
}

public class WaypointManager : MonoBehaviour
{
    public GameObject waypointPrefab;
    private List<Waypoint> waypoints = new List<Waypoint>();
    public TextMeshProUGUI statusText;
    public PressableButtonHoloLens2 deleteAllButton;
    public PressableButtonHoloLens2 doneEditButton;
    private Waypoint currentEditingWaypoint;

    public WaypointMode Mode { get; private set; } = WaypointMode.Idle;

    private const int MAX_WAYPOINTS = 5;

    private void Start()
    {
        deleteAllButton.ButtonPressed.AddListener(DeleteAllWaypoints);
        UpdateStatus("Create mode active. Tap to add waypoints.");
    }

    public void SetMode(WaypointMode newMode)
    {
        Mode = newMode;
        Debug.Log("Waypoint mode changed to: " + Mode);
        UpdateStatus((Mode == WaypointMode.Delete) ? "Delete mode active. Tap waypoints to remove." : 
                     (Mode == WaypointMode.Create) ? "Create mode active. Tap to add waypoints." : 
                     "Edit mode active. Tap waypoints to edit.");
        foreach (var waypoint in waypoints)
        {
            if (Mode == WaypointMode.Delete)
                waypoint.setColor();
            else
                waypoint.resetColor();
        }
    }

    public void AddWaypoint(Vector3 position, Quaternion rotation)
    {
        if (Mode != WaypointMode.Create)
        {
            UpdateStatus("Switch to Create mode to add waypoints.");
            return;
        }

        if (waypoints.Count >= MAX_WAYPOINTS)
        {
            UpdateStatus("Maximum of 2 waypoints reached.");
            return;
        }

        GameObject wpObj = Instantiate(waypointPrefab, position, rotation);
        Waypoint wp = wpObj.GetComponent<Waypoint>();
        waypoints.Add(wp);
        RefreshOrders();
        UpdateStatus($"Waypoint {waypoints.Count} created.");
    }

    public void StartEdit (Waypoint waypoint)
    {
        doneEditButton.gameObject.SetActive(true);
        waypoint.StartEditing();
        currentEditingWaypoint = waypoint;
    }

    public void StopEdit ()
    {
        doneEditButton?.gameObject.SetActive(false);
        if (currentEditingWaypoint != null)
            currentEditingWaypoint.StopEditing();
        currentEditingWaypoint = null;
    }

    public void RemoveWaypoint(Waypoint wp)
    {
        if (!waypoints.Contains(wp)) return;

        waypoints.Remove(wp);
        Destroy(wp.gameObject);
        RefreshOrders();
        UpdateStatus($"Waypoint removed. {waypoints.Count} remaining.");
    }

    public void DeleteAllWaypoints()
    {
        foreach (var wp in waypoints)
        {
            Destroy(wp.gameObject);
        }
        waypoints.Clear();
        UpdateStatus("All waypoints deleted.");
    }

    private void RefreshOrders()
    {
        for (int i = 0; i < waypoints.Count; i++)
        {
            waypoints[i].SetOrder(i + 1);
            waypoints[i].UpdateState();
        }
    }

    private void UpdateStatus(string message)
    {
        if (statusText != null)
            statusText.text = message;
        Debug.Log(message);
    }

    public List<Waypoint> GetWaypoints() => waypoints;

    /// <summary>
    /// Resolves an authoring command's `reference` field ("last", a 1-indexed
    /// integer as a string, or null/empty) to a Waypoint. Distinguishes
    /// "no reference given" from "that waypoint doesn't exist" so callers can
    /// give different feedback for each -- see ReferenceResolution.
    /// </summary>
    public ReferenceResolution TryGetWaypointByReference(string reference, out Waypoint wp)
    {
        wp = null;

        if (string.IsNullOrEmpty(reference))
            return ReferenceResolution.Missing;

        if (reference == "last")
        {
            if (waypoints.Count == 0)
                return ReferenceResolution.OutOfRange;
            wp = waypoints[waypoints.Count - 1];
            return ReferenceResolution.Resolved;
        }

        if (int.TryParse(reference, out int index) && index >= 1 && index <= waypoints.Count)
        {
            wp = waypoints[index - 1];
            return ReferenceResolution.Resolved;
        }

        return ReferenceResolution.OutOfRange;
    }

    /// <summary>
    /// Applies a UR10-base-frame offset (SI units: meters for x/y/z) to a
    /// waypoint, converting into Unity's local space relative to robotBase.
    /// This is the INVERSE of the conversion in
    /// OperationsManager.CalculateWaypointsData() -- that is the canonical,
    /// live Unity->UR conversion (UR.x=Unity.z, UR.y=-Unity.x, UR.z=Unity.y);
    /// a second, dead/commented conversion elsewhere in OperationsManager.cs
    /// uses different signs and must NOT be used as a reference here.
    ///
    /// Rotation axes (rx/ry/rz) are not implemented -- composing an
    /// axis-angle offset in UR frame back onto the waypoint's quaternion is
    /// materially more complex than translation and is deferred past Stage 1
    /// (tracked as required before the demo video). Returns UnsupportedAxis
    /// rather than silently no-op'ing or misapplying.
    /// </summary>
    public OffsetResult TryApplyOffset(Waypoint wp, string axis, float value, Transform robotBase)
    {
        Vector3 localDelta;
        switch (axis)
        {
            case "x": localDelta = new Vector3(0f, 0f, value); break;   // UR x -> Unity local z (forward)
            case "y": localDelta = new Vector3(-value, 0f, 0f); break;  // UR y -> Unity local -x (operator's left)
            case "z": localDelta = new Vector3(0f, value, 0f); break;   // UR z -> Unity local y (up)
            case "rx":
            case "ry":
            case "rz":
                return OffsetResult.UnsupportedAxis;
            default:
                return OffsetResult.UnsupportedAxis;
        }

        Vector3 localPos = robotBase.InverseTransformPoint(wp.transform.position);
        wp.transform.position = robotBase.TransformPoint(localPos + localDelta);
        return OffsetResult.Applied;
    }
}
