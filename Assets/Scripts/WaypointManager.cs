using System;
using System.Collections.Generic;
using UnityEngine;

public class WaypointManager : MonoBehaviour
{
    public GameObject waypointPrefab;
    private List<Waypoint> waypoints = new List<Waypoint>();

    public void AddWaypoint(Vector3 position, Quaternion rotation)
    {
        GameObject wpObj = Instantiate(waypointPrefab, position, rotation);
        Waypoint wp = wpObj.GetComponent<Waypoint>();
        waypoints.Add(wp);
        RefreshOrders();
    }

    public void RemoveWaypoint(Waypoint wp)
    {
        waypoints.Remove(wp);
        Destroy(wp.gameObject);
        RefreshOrders();
    }

    private void RefreshOrders()
    {
        for (int i = 0; i < waypoints.Count; i++)
        {
            waypoints[i].SetOrder(i + 1);
            waypoints[i].UpdateState();
        }
    }

    // Optional: expose waypoints for robot system
    public List<Waypoint> GetWaypoints() => waypoints;
}
