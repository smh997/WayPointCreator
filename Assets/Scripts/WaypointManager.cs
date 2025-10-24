using System.Collections.Generic;
using UnityEngine;
using TMPro;
using UnityEngine.UI;
using Microsoft.MixedReality.Toolkit.UI;

public class WaypointManager : MonoBehaviour
{
    public GameObject waypointPrefab;
    private List<Waypoint> waypoints = new List<Waypoint>();
    public TextMeshProUGUI statusText;
    public PressableButtonHoloLens2 deleteAllButton; // UI button in panel

    public bool DeleteMode { get; private set; } = false;
    private const int MAX_WAYPOINTS = 2;

    private void Start()
    {
        deleteAllButton.ButtonPressed.AddListener(DeleteAllWaypoints);
        UpdateStatus("Create mode active. Tap to add waypoints.");
    }

    public void SetDeleteMode(bool isDelete)
    {
        DeleteMode = isDelete;
        UpdateStatus(DeleteMode
            ? "Delete mode active. Tap waypoints to remove."
            : "Create mode active. Tap to add waypoints.");
    }

    public void AddWaypoint(Vector3 position, Quaternion rotation)
    {
        if (DeleteMode)
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
