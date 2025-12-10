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
}
