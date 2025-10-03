using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.Utilities;
using Preliy.Flange;
using System.Collections.Generic;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

public enum PlacementPhase
{
    RobotInit,
    Calibration,
    Waypoint
}

[System.Serializable]
public class RobotState
{
    public float[] joints;
    public float[] tcp; // [x, y, z, rx, ry, rz]
}

public class FingerWaypointPlacer : MonoBehaviour
{
    [Header("References")]
    public WaypointManager waypointManager;
    public GameObject waypointPreviewPrefab;
    public Transform robotBase;
    //public Transform robotEndEffector;
    public GameObject calibrationCanvas;
    public Controller robotController; // assign your controller here
    private Robot robot;

    [Header("Settings")]
    public Handedness handToUse = Handedness.Right;
    public float pinchCooldown = 0.5f;

    [Header("Networking")]
    public string serverIP = "192.168.0.100";
    public int serverPort = 5000;

    [Header("Clap Gesture Settings")]
    public float clapDistanceThreshold = 0.1f;
    public float clapSpeedThreshold = 0.05f;

    private GameObject previewInstance;
    private float lastPlaceTime = 0f;
    private List<string> localWaypoints = new List<string>();

    private Vector3 lastLeftPos;
    private Vector3 lastRightPos;

    public PlacementPhase currentPhase = PlacementPhase.RobotInit;

    void Start()
    {
        // Instantiate preview
        if (waypointPreviewPrefab != null)
        {
            previewInstance = Instantiate(waypointPreviewPrefab);
            previewInstance.SetActive(false);
        }
        Debug.Log($"Robot base position: {robotBase.position}");

        // Start sequentially
        StartCoroutine(SequentialFlow());
    }

    private System.Collections.IEnumerator SequentialFlow()
    {
        // --- ROBOT INIT ---
        Debug.Log("Connecting to robot and fetching initial state...");
        RobotState state = GetRobotState();
        UpdateDigitalTwin(state);
        Debug.Log("Robot initialized.");
        yield return new WaitForSeconds(0.5f); // small delay for visual stability

        // --- CALIBRATION ---
        SetPhase(PlacementPhase.Calibration);
        Debug.Log("Waiting for calibration clap...");
        while (!IsTwoHandClap())
        {
            yield return null; // wait until clap detected
        }
        Debug.Log("Calibration complete.");
        Debug.Log($"CHanged: Robot base position: {robotBase.position}");
        yield return new WaitForSeconds(0.2f);

        // --- WAYPOINT PLACEMENT ---
        SetPhase(PlacementPhase.Waypoint);
        Debug.Log("Waypoint phase started. Pinch to place waypoints, clap to send all.");

        // Stay in Waypoint phase indefinitely
        while (true)
        {
            HandleWaypointPlacement();
            if (IsTwoHandClap())
            {
                SendAllWaypoints();
            }
            yield return null;
        }
    }

    #region Robot Communication (Sequential)
    private RobotState GetRobotState()
    {
        try
        {
            using (TcpClient client = new TcpClient(serverIP, serverPort))
            using (NetworkStream stream = client.GetStream())
            {
                // Read up to 1024 bytes
                byte[] buffer = new byte[1024];
                int bytesRead = stream.Read(buffer, 0, buffer.Length);
                string json = Encoding.UTF8.GetString(buffer, 0, bytesRead);
                RobotState state = JsonUtility.FromJson<RobotState>(json);
                return state;
            }
        }
        catch (SocketException e)
        {
            Debug.LogError("Failed to connect to robot: " + e.Message);
            return new RobotState(); // empty fallback
        }
    }

    private void UpdateDigitalTwin(RobotState state)
    {
        if (robotController == null)
        {
            Debug.LogWarning("RobotController not assigned!");
            return;
        }

        // Assuming your RobotController has a MechanicalGroup.Robot object
        robot = robotController.MechanicalGroup.Robot;

        if (state.joints != null && state.joints.Length > 0)
        {
            // Update robot joint values
            robot.Joints.SetJointValues(state.joints);
            Debug.Log("Robot joints updated from digital twin.");
        }
        else
        {
            Debug.LogWarning("RobotState has no joint data.");
        }

        //if (state.tcp != null && state.tcp.Length >= 6)
        //{
        //    // Optionally update end-effector pose if needed
        //    Vector3 position = new Vector3(state.tcp[0], state.tcp[1], state.tcp[2]);
        //    Vector3 rotationEuler = new Vector3(state.tcp[3], state.tcp[4], state.tcp[5]);
        //    robot.EndEffector.SetPose(position, Quaternion.Euler(rotationEuler));
        //    Debug.Log("Robot TCP (pose) updated from digital twin.");
        //}
        //else
        //{
        //    Debug.LogWarning("RobotState has incomplete TCP data.");
        //}

    }
    #endregion

    #region Waypoint Placement
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

                // Unity → UR10
                Vector3 localPosUnity = robotBase.InverseTransformPoint(pose.Position);
                Vector3 localPosUR = new Vector3(-localPosUnity.z, -localPosUnity.x, localPosUnity.y);
                Quaternion localRotUnity = Quaternion.Inverse(robotBase.rotation) * pose.Rotation;

                // Convert to axis-angle rotation vector
                Vector3 rvec = QuaternionToRotationVector(localRotUnity);

                string waypointJson = $"{{\"x\":{localPosUR.x},\"y\":{localPosUR.y},\"z\":{localPosUR.z}," +
                                      $"\"rx\":{rvec.x},\"ry\":{rvec.y},\"rz\":{rvec.z}}}";
                localWaypoints.Add(waypointJson);

                Debug.Log("Waypoint (UR coords with rotation vector): " + waypointJson);

                Debug.Log($"waypoint world pose: {pose.Position}");
                Debug.Log($"Robot base position: {robotBase.position}");
                lastPlaceTime = Time.time;
            }
        }
        else
        {
            if (previewInstance != null)
                previewInstance.SetActive(false);
        }
    }

    // Convert Quaternion → axis-angle vector for UR10
    private Vector3 QuaternionToRotationVector(Quaternion q)
    {
        // Ensure quaternion is normalized
        if (q.w > 1) q.Normalize();

        float angle = 2.0f * Mathf.Acos(q.w);
        float s = Mathf.Sqrt(1 - q.w * q.w);

        // Avoid divide by zero
        if (s < 0.001f)
            return new Vector3(q.x, q.y, q.z) * angle;
        else
            return new Vector3(q.x / s, q.y / s, q.z / s) * angle;
    }


    private bool IsPinching(Handedness hand)
    {
        if (HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, hand, out MixedRealityPose indexPose) &&
            HandJointUtils.TryGetJointPose(TrackedHandJoint.ThumbTip, hand, out MixedRealityPose thumbPose))
        {
            return Vector3.Distance(indexPose.Position, thumbPose.Position) < 0.02f;
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

            lastLeftPos = leftPos;
            lastRightPos = rightPos;

            return distance < clapDistanceThreshold && approachSpeed > clapSpeedThreshold;
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
        byte[] data = Encoding.UTF8.GetBytes(jsonArray + "\n");

        try
        {
            using (TcpClient client = new TcpClient(serverIP, serverPort))
            using (NetworkStream stream = client.GetStream())
            {
                stream.Write(data, 0, data.Length);
                Debug.Log("Sent all waypoints: " + jsonArray);
            }
        }
        catch (SocketException e)
        {
            Debug.LogError("Send failed: " + e.Message);
        }
    }
    #endregion

    private void SetPhase(PlacementPhase newPhase)
    {
        currentPhase = newPhase;
        if (calibrationCanvas != null)
            calibrationCanvas.SetActive(newPhase == PlacementPhase.Calibration);
        if (previewInstance != null)
            previewInstance.SetActive(newPhase == PlacementPhase.Waypoint);
    }
}
