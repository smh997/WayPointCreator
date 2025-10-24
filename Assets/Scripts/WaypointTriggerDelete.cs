using UnityEngine;

public class WaypointTriggerDelete : MonoBehaviour
{
    private WaypointManager manager;

    void Start()
    {
        // Find the manager in the scene (or assign it manually in the Inspector)
        manager = FindObjectOfType<WaypointManager>();
    }

    private void OnTriggerEnter(Collider other)
    {
        // Optional: filter by hand tags or layers if you have hand colliders in a specific layer
        if (manager != null && manager.DeleteMode)
        {
            var wp = GetComponent<Waypoint>();
            if (wp != null)
            {
                manager.RemoveWaypoint(wp);
            }
        }
    }
}
