using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.Utilities;
using UnityEngine;
using System.Net.Sockets;
using System.Text;
using System.Collections.Generic;

public enum PlacementPhase
{
    Calibration,
    Waypoint
}

public class FingerWaypointPlacer : MonoBehaviour
{
    [Header("References")]
    public WaypointManager waypointManager;
    public GameObject waypointPreviewPrefab;
    public Transform robotBase;
    public GameObject calibrationCanvas; // assign your calibration UI canvas here

    [Header("Settings")]
    public Handedness handToUse = Handedness.Right;
    public float pinchCooldown = 0.5f;

    [Header("Networking")]
    public string serverIP = "192.168.0.104";
    public int serverPort = 5000;

    [Header("Clap Gesture Settings")]
    public float clapDistanceThreshold = 0.1f;
    public float clapSpeedThreshold = 0.05f;

    private GameObject previewInstance;
    private float lastPlaceTime = 0f;
    private List<string> localWaypoints = new List<string>();

    private Vector3 lastLeftPos;
    private Vector3 lastRightPos;

    // Phase state
    public PlacementPhase currentPhase = PlacementPhase.Calibration;

    void Start()
    {
        if (waypointPreviewPrefab != null)
        {
            previewInstance = Instantiate(waypointPreviewPrefab);
            previewInstance.SetActive(false);
        }

        SetPhase(PlacementPhase.Calibration); // start in calibration mode
    }

    void Update()
    {
        if (currentPhase == PlacementPhase.Calibration)
        {
            // Only one-time calibration, waiting for clap
            if (IsTwoHandClap())
            {
                Debug.Log("Clap detected → Calibration complete, switching to Waypoint Phase");
                SetPhase(PlacementPhase.Waypoint);
            }
        }
        else if (currentPhase == PlacementPhase.Waypoint)
        {
            HandleWaypointPlacement();

            if (IsTwoHandClap())
            {
                Debug.Log("Clap detected → Sending waypoints");
                SendAllWaypoints();
                // stay in Waypoint phase, no going back
            }
        }
    }

    private void HandleWaypointPlacement()
    {
        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, handToUse, out MixedRealityPose pose))
        {
            if (previewInstance != null)
            {
                previewInstance.SetActive(true);
                previewInstance.transform.position = pose.Position;
                previewInstance.transform.rotation = pose.Rotation;
            }

            if (IsPinching(handToUse) && Time.time - lastPlaceTime > pinchCooldown)
            {
                waypointManager.AddWaypoint(pose.Position, pose.Rotation);

                // Relative position in Unity robot frame
                Vector3 localPosUnity = robotBase.InverseTransformPoint(pose.Position);

                // Convert to UR10 convention (swap Y/Z)
                Vector3 localPosUR = new Vector3(
                    -localPosUnity.x,
                    -localPosUnity.z,  // Unity Z → UR Y
                    localPosUnity.y   // Unity Y → UR Z
                );

                // Relative rotation (Unity frame)
                Quaternion localRotUnity = Quaternion.Inverse(robotBase.rotation) * pose.Rotation;

                // Axis swap for rotation (basic swap Y/Z)
                Quaternion localRotUR = new Quaternion(
                    localRotUnity.x,
                    localRotUnity.z,  // swap
                    localRotUnity.y,  // swap
                    localRotUnity.w
                );

                string waypointJson = $"{{\"x\":{localPosUR.x},\"y\":{localPosUR.y},\"z\":{localPosUR.z}," +
                                      $"\"qx\":{localRotUR.x},\"qy\":{localRotUR.y},\"qz\":{localRotUR.z},\"qw\":{localRotUR.w}}}";

                localWaypoints.Add(waypointJson);
                Debug.Log("Waypoint saved locally (UR coords): " + waypointJson);

                lastPlaceTime = Time.time;
                //waypointManager.AddWaypoint(pose.Position, pose.Rotation);

                //Vector3 localPos = robotBase.InverseTransformPoint(pose.Position);
                //Quaternion localRot = Quaternion.Inverse(robotBase.rotation) * pose.Rotation;

                //string waypointJson = $"{{\"x\":{localPos.x},\"y\":{localPos.y},\"z\":{localPos.z}," +
                //                      $"\"qx\":{localRot.x},\"qy\":{localRot.y},\"qz\":{localRot.z},\"qw\":{localRot.w}}}";

                //localWaypoints.Add(waypointJson);
                //Debug.Log("Waypoint saved locally: " + waypointJson);

                //lastPlaceTime = Time.time;
            }
        }
        else
        {
            if (previewInstance != null)
                previewInstance.SetActive(false);
        }
    }

    private bool IsPinching(Handedness hand)
    {
        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, hand, out MixedRealityPose indexPose) &&
            HandJointUtils.TryGetJointPose(TrackedHandJoint.ThumbTip, hand, out MixedRealityPose thumbPose))
        {
            float distance = Vector3.Distance(indexPose.Position, thumbPose.Position);
            return distance < 0.02f;
        }
        return false;
    }

    private bool IsTwoHandClap()
    {
        bool leftPresent = HandJointUtils.TryGetJointPose(TrackedHandJoint.Palm, Handedness.Left, out MixedRealityPose leftPose);
        bool rightPresent = HandJointUtils.TryGetJointPose(TrackedHandJoint.Palm, Handedness.Right, out MixedRealityPose rightPose);

        if (leftPresent && rightPresent)
        {
            Vector3 leftPos = leftPose.Position;
            Vector3 rightPos = rightPose.Position;

            float distance = Vector3.Distance(leftPos, rightPos);

            float leftSpeed = Vector3.Distance(leftPos, lastLeftPos);
            float rightSpeed = Vector3.Distance(rightPos, lastRightPos);
            float approachSpeed = (leftSpeed + rightSpeed) / Time.deltaTime;

            if (distance < clapDistanceThreshold && approachSpeed > clapSpeedThreshold)
            {
                return true;
            }
            lastLeftPos = leftPos;
            lastRightPos = rightPos;
        }
        return false;
    }

    public void SendAllWaypoints()
    {
        if (localWaypoints.Count == 0)
        {
            Debug.Log("No waypoints to send.");
            return;
        }

        string jsonArray = "[" + string.Join(",", localWaypoints) + "]";
        Debug.Log("Preparing to send waypoints:\n" + jsonArray);

        byte[] data = Encoding.UTF8.GetBytes(jsonArray + "\n");

        try
        {
            using (TcpClient client = new TcpClient(serverIP, serverPort))
            using (NetworkStream stream = client.GetStream())
            {
                Debug.Log("Sent all waypoints: " + jsonArray);
                stream.Write(data, 0, data.Length);
            }
        }
        catch (SocketException e)
        {
            Debug.LogError("Send failed: " + e.Message);
        }

        //localWaypoints.Clear();
    }

    private void SetPhase(PlacementPhase newPhase)
    {
        currentPhase = newPhase;

        // Only show calibration canvas in Calibration phase
        if (calibrationCanvas != null)
            calibrationCanvas.SetActive(newPhase == PlacementPhase.Calibration);

        // Preview waypoint indicator only in Waypoint phase
        if (previewInstance != null)
            previewInstance.SetActive(newPhase == PlacementPhase.Waypoint);
    }
}
