using Microsoft.MixedReality.Toolkit.Input;
using Microsoft.MixedReality.Toolkit.UI;
using Microsoft.MixedReality.Toolkit.Utilities;
using Preliy.Flange;
using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Net.Sockets;
using System.Text;
using TMPro;
using UnityEngine;

public enum PlacementPhase
{
    Idle,
    Calibration,
    Waypoint,
    Preview
}

public enum PreviewAction
{
    None,
    Preview,
    Run,
    Exit
}

[System.Serializable]
public class JointSolution
{
    public float[] joints;
}


[System.Serializable]
public class PreviewTrajectory
{
    public bool success;
    public string message;
    public List<JointSolution> jointSolutions;
}

[System.Serializable]
public class RunResult
{
    public bool success;
    public string message;
    public RobotState robotState;
}



[System.Serializable]
public class RobotState
{
    public float[] joints;
    public float[] tcp; // [x, y, z, rx, ry, rz]
}

public class OperationsManager : MonoBehaviour
{
    [Header("References")]
    public WaypointManager waypointManager;
    public GameObject waypointPreviewPrefab;
    public Transform robotBase;
    //public Transform robotEndEffector;
    public GameObject calibrationCanvas;
    public GameObject WaypointCanvas;
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

    private Vector3 lastLeftPos;
    private Vector3 lastRightPos;

    public PlacementPhase currentPhase = PlacementPhase.Idle;
    public PreviewAction previewAction = PreviewAction.None;

    public TextMeshProUGUI PreviewRunStatusText;

    private bool robotFinishedExecuting = true;
    private PreviewTrajectory previewResult = null;
    private bool previewFinished = false;
    private RunResult runResult= null;

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
        Debug.Log("Connecting to robot and fetching initial state...");
        RobotState state = GetRobotState();
        UpdateDigitalTwin(state);
        Debug.Log("Robot initialized.");
        StartCoroutine(SequentialFlow());
    }

    private System.Collections.IEnumerator SequentialFlow()
    {
        while (true)
        {
            // --- IDLE ---
            if (currentPhase == PlacementPhase.Idle)
            {
                yield return null;
            }
            // --- CALIBRATION ---
            else if (currentPhase == PlacementPhase.Calibration)
            {
                waypointManager.DeleteAllWaypoints();
                Debug.Log("Waiting for calibration...");
                while (currentPhase == PlacementPhase.Calibration)
                {
                    yield return null;
                }
                Debug.Log("Calibration complete.");
                Debug.Log($"Changed: Robot base position: {robotBase.position}");
                yield return new WaitForSeconds(0.2f);
            }
            // --- WAYPOINT PLACEMENT ---
            else if (currentPhase == PlacementPhase.Waypoint)
            {
                Debug.Log("Waypoint phase started. Pinch to place waypoints.");

                while (currentPhase == PlacementPhase.Waypoint)
                {
                    HandleWaypointPlacement();
                    yield return null;
                }
            }
            // --- Preview/Run ---
            else if (currentPhase == PlacementPhase.Preview)
            {
                Debug.Log("Preview/Run phase… waiting for user action");

                // Here we wait until the user presses:
                //   - PREVIEW button
                //   - RUN button
                //   - EXIT button (back to main menu)
                previewAction = PreviewAction.None;

                while (currentPhase == PlacementPhase.Preview)
                {
                    if (previewAction == PreviewAction.Preview)
                    {
                        yield return StartCoroutine(HandlePreview());
                        previewAction = PreviewAction.None;
                    }
                    else if (previewAction == PreviewAction.Run)
                    {
                        yield return StartCoroutine(HandleRun());
                        previewAction = PreviewAction.None;
                    }
                    else if (previewAction == PreviewAction.Exit)
                    {
                        Debug.Log("Exiting Preview/Run");
                        currentPhase = PlacementPhase.Idle;
                    }

                    yield return null;
                }
            }
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
                // ---- 1) Send request for robot state ----
                string request = "{\"type\":\"robot_state\"}\n";
                byte[] reqBytes = Encoding.UTF8.GetBytes(request);
                stream.Write(reqBytes, 0, reqBytes.Length);

                // ---- 2) Read server response ----
                byte[] buffer = new byte[4096];
                int bytesRead = stream.Read(buffer, 0, buffer.Length);

                if (bytesRead <= 0)
                {
                    Debug.LogError("RobotState: No response from server.");
                    return new RobotState();
                }

                string json = Encoding.UTF8.GetString(buffer, 0, bytesRead).Trim();
                Debug.Log("RobotState JSON received: " + json);

                // ---- 3) Parse cleanly ----
                RobotState state = JsonUtility.FromJson<RobotState>(json);
                return state;
            }
        }
        catch (Exception e)
        {
            Debug.LogError("Failed to get robot state: " + e.Message);
            return new RobotState();
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
        if (waypointManager.Mode == WaypointMode.Create && HandJointUtils.TryGetJointPose(TrackedHandJoint.IndexTip, handToUse, out MixedRealityPose pose))
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
                //localWaypoints.Add(waypointJson);

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

    //private bool IsTwoHandClap()
    //{
    //    bool leftPresent = HandJointUtils.TryGetJointPose(TrackedHandJoint.Palm, Handedness.Left, out MixedRealityPose leftPose);
    //    bool rightPresent = HandJointUtils.TryGetJointPose(TrackedHandJoint.Palm, Handedness.Right, out MixedRealityPose rightPose);

    //    if (leftPresent && rightPresent)
    //    {
    //        Vector3 leftPos = leftPose.Position;
    //        Vector3 rightPos = rightPose.Position;
    //        float distance = Vector3.Distance(leftPos, rightPos);
    //        float leftSpeed = Vector3.Distance(leftPos, lastLeftPos);
    //        float rightSpeed = Vector3.Distance(rightPos, lastRightPos);
    //        float approachSpeed = (leftSpeed + rightSpeed) / Time.deltaTime;

    //        lastLeftPos = leftPos;
    //        lastRightPos = rightPos;

    //        return distance < clapDistanceThreshold && approachSpeed > clapSpeedThreshold;
    //    }
    //    return false;
    //}



    #endregion

    public byte[] CalculateWaypointsData()
    {
        if (waypointManager.GetWaypoints().Count == 0)
        {
            Debug.Log("No waypoints to send.");
            return null;
        }

        List<string> localWaypoints = new List<string>();

        foreach (var wp in waypointManager.GetWaypoints())
        {
            Vector3 localPosUnity = robotBase.InverseTransformPoint(wp.transform.position);
            Vector3 localPosUR = new Vector3(localPosUnity.z, -localPosUnity.x, localPosUnity.y);
            //Vector3 localPosUR = new Vector3(-localPosUnity.x, -localPosUnity.z, localPosUnity.y);
            Debug.Log($"waypoint {wp.orderText}: unity({localPosUnity.x}, {localPosUnity.y}, {localPosUnity.z})\n real({localPosUR.x}, {localPosUR.y}, {localPosUR.z})");
            Quaternion localRotUnity = Quaternion.Inverse(robotBase.rotation) * wp.transform.rotation;
            Vector3 rvec = QuaternionToRotationVector(localRotUnity);

            string waypointJson = $"{{\"x\":{localPosUR.x},\"y\":{localPosUR.y},\"z\":{localPosUR.z}," +
                                  $"\"rx\":{rvec.x},\"ry\":{rvec.y},\"rz\":{rvec.z}}}";
            localWaypoints.Add(waypointJson);
        }

        string jsonArray = "[" + string.Join(",", localWaypoints) + "]";
        byte[] data = Encoding.UTF8.GetBytes(jsonArray + "\n");
        Debug.Log("Sent all waypoints: " + jsonArray);

        return data;
    }

    //public void SendAllWaypoints()
    //{
    //    byte[] data = CalculateWaypointsData();

    //    if (data == null)
    //        return;
    //    try
    //    {
    //        using (TcpClient client = new TcpClient(serverIP, serverPort))
    //        using (NetworkStream stream = client.GetStream())
    //        {
    //            stream.Write(data, 0, data.Length); 
    //        }
    //    }
    //    catch (SocketException e)
    //    {
    //        Debug.LogError("Send failed: " + e.Message);
    //    }
    //}

    private IEnumerator HandlePreview()
    {
        if (waypointManager.GetWaypoints().Count == 0)
        {
            UpdatePreviewStatus("No waypoints to preview.");
            yield break;
        }

        UpdatePreviewStatus("Requesting preview…");

        previewFinished = false;
        StartCoroutine(RequestPreviewCoroutine());

        yield return new WaitUntil(() => previewFinished);

        if (previewResult == null)
        {
            UpdatePreviewStatus("Preview failed: no response.");
            yield break;
        }

        // Show server message first
        if (!string.IsNullOrEmpty(previewResult.message))
        {
            UpdatePreviewStatus(previewResult.message);
            yield return new WaitForSeconds(1f); // optional pause to let user read
        }

        if (!previewResult.success)
        {
            UpdatePreviewStatus($"Unreachable waypoints: {previewResult.message}");
            yield break;
        }

        UpdatePreviewStatus("Animating digital twin…");

        List<JointSolution> jointTrajectory = previewResult.jointSolutions;

        foreach (JointSolution jointTrajectoryItem in jointTrajectory)
        {
            for (int i = 0; i < 6; i++)
            {
                jointTrajectoryItem.joints[i] = jointTrajectoryItem.joints[i] * Mathf.Rad2Deg;
            }
        }
        yield return StartCoroutine(AnimatePreviewSmooth(jointTrajectory, stepTime: 2f, subSteps: 20));

        UpdatePreviewStatus("Preview complete.");
    }




    private IEnumerator HandleRun()
    {
        Debug.Log("RUN requested.");

        if (waypointManager.GetWaypoints().Count == 0)
        {
            UpdatePreviewStatus("No waypoints to run.");
            yield break;
        }

        UpdatePreviewStatus("Sending trajectory to robot…");

        StartCoroutine(SendAllWaypointsCoroutine());

        yield return new WaitUntil(() => robotFinishedExecuting);

        if (runResult != null)
        {
            UpdatePreviewStatus(runResult.message);
            if (runResult.robotState != null)
            {
                RobotState state = runResult.robotState;
                UpdateDigitalTwin(state);
            }
        }
        else
            UpdatePreviewStatus("Execution finished, no server message.");
    }



    private void UpdatePreviewStatus(string message)
    {
        if (PreviewRunStatusText != null)
            PreviewRunStatusText.text = message;
        Debug.Log(message);
    }


    public IEnumerator SendAllWaypointsCoroutine()
    {
        byte[] waypointData = CalculateWaypointsData();
        if (waypointData == null)
            yield break;

        runResult = null;
        robotFinishedExecuting = false;

        try
        {
            using (TcpClient client = new TcpClient(serverIP, serverPort))
            using (NetworkStream stream = client.GetStream())
            {
                // Wrap waypoint array into a JSON object with type = "run"
                string jsonMsg = "{\"type\":\"run\",\"waypoints\":" + Encoding.UTF8.GetString(waypointData).Trim() + "}\n";
                byte[] data = Encoding.UTF8.GetBytes(jsonMsg);

                // 1) Send waypoints
                stream.Write(data, 0, data.Length);

                // 2) Wait for server response
                byte[] buffer = new byte[4096];
                int bytesRead = stream.Read(buffer, 0, buffer.Length);

                if (bytesRead > 0)
                {
                    string json = Encoding.UTF8.GetString(buffer, 0, bytesRead).Trim();
                    Debug.Log("Robot server response: " + json);

                    // Deserialize to RunResult
                    try
                    {
                        runResult = JsonUtility.FromJson<RunResult>(json);
                    }
                    catch (Exception e)
                    {
                        Debug.LogError("Failed to parse RunResult: " + e.Message);
                        runResult = new RunResult { success = false, message = "Failed to parse server response.", robotState = null };
                    }
                }
                else
                {
                    runResult = new RunResult { success = false, message = "No response from server.", robotState = null };
                }

                robotFinishedExecuting = true;
            }
        }
        catch (Exception e)
        {
            Debug.LogError("Send failed: " + e.Message);
            runResult = new RunResult { success = false, message = "Send failed: " + e.Message, robotState = null };
            robotFinishedExecuting = true;
        }
    }


    public IEnumerator RequestPreviewCoroutine()
    {
        previewFinished = false;
        previewResult = null;

        byte[] waypointData = CalculateWaypointsData();
        if (waypointData == null)
            yield break;

        try
        {
            using (TcpClient client = new TcpClient(serverIP, serverPort))
            using (NetworkStream stream = client.GetStream())
            {
                // Wrap waypoint array into a JSON object with type = "preview"
                string jsonMsg = "{\"type\":\"preview\",\"waypoints\":" + Encoding.UTF8.GetString(waypointData).Trim() + "}\n";
                byte[] data = Encoding.UTF8.GetBytes(jsonMsg);

                // 1) Send preview request
                stream.Write(data, 0, data.Length);

                // 2) Read server response
                byte[] buffer = new byte[4096];
                int bytesRead = stream.Read(buffer, 0, buffer.Length);

                if (bytesRead > 0)
                {
                    string json = Encoding.UTF8.GetString(buffer, 0, bytesRead).Trim();
                    Debug.Log("Preview JSON received: " + json);

                    // Server returns:
                    // {"success":true,"message":"All waypoints reachable.","jointSolutions":[[...],[...]]}
                    previewResult = JsonUtility.FromJson<PreviewTrajectory>(json);
                    previewFinished = true;
                    Debug.Log($"Preview Result:\n success: {previewResult.success}, msg: {previewResult.message}, joints: {previewResult.jointSolutions}, {previewResult.jointSolutions[0].joints[0]}");
                }
            }
        }
        catch (Exception e)
        {
            Debug.LogError("Preview request failed: " + e.Message);
            previewFinished = true;
        }
    }


    private IEnumerator AnimatePreviewSmooth(List<JointSolution> trajectory, float stepTime = 1f, int subSteps = 10)
    {
        if (trajectory == null || trajectory.Count == 0)
            yield break;
        JointSolution robotJoints = new JointSolution();
        robotJoints.joints = new float[6];
        //Debug.Log("here");
        for (int i = 0; i < 6; i++) {
            robotJoints.joints[i] = robot.GetJointValues()[i];
        }
        //Debug.Log("here2");
        trajectory.Insert(0, robotJoints);
        robot.Joints.SetJointValues(robotJoints.joints);
        //Debug.Log("here3" + trajectory.Count);
        for (int i = 0; i < trajectory.Count - 1; i++)
        {
            float[] start = trajectory[i].joints;
            float[] end = trajectory[i + 1].joints;
            List<string> startJoints = new List<string>();
            List<string> endJoints = new List<string>();
            foreach (var joint in start)
            {
                startJoints.Add(joint.ToString());
            }
            foreach (var joint in end)
            {
                endJoints.Add(joint.ToString());
            }

            //Debug.Log($"start: {string.Join(" ", startJoints)}, end: {string.Join(" ", endJoints)};");

            for (int s = 0; s <= subSteps; s++)
            {
                float t = s / (float)subSteps;
                float[] interp = new float[6];
                for (int j = 0; j < 6; j++)
                    interp[j] = Mathf.Lerp(start[j], end[j], t);
                robot.Joints.SetJointValues(interp);  // Update digital twin
                yield return new WaitForSeconds(stepTime / subSteps);
            }
        }

        // Ensure last pose is exact
        robot.Joints.SetJointValues(trajectory[trajectory.Count - 1].joints);
        yield return new WaitForSeconds(1f);
        robot.Joints.SetJointValues(robotJoints.joints);
    }



    public void SetPhase(PlacementPhase newPhase)
    {
        currentPhase = newPhase;

        if (calibrationCanvas != null)
            calibrationCanvas.SetActive(newPhase == PlacementPhase.Calibration);

        if (previewInstance != null)
        {
            bool showPreview = newPhase == PlacementPhase.Waypoint
                               && waypointManager.Mode == WaypointMode.Create; // only show preview if creating
            previewInstance.SetActive(showPreview);
        }
        if (WaypointCanvas != null)
            WaypointCanvas.SetActive(newPhase == PlacementPhase.Waypoint);

        ObjectManipulator objectManipulator = robotController.MechanicalGroup.Robot.GetComponent<ObjectManipulator>();
        if (objectManipulator != null)
            objectManipulator.enabled = (newPhase == PlacementPhase.Calibration);
    }

}
