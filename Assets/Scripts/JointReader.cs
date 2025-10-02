using Preliy.Flange;
using System.Collections.Generic;
using System.Text;
using UnityEngine;
using UnityEngine.UIElements;

public class JointReader : MonoBehaviour
{
    [Tooltip("Assign in inspector or it will find the first Controller in scene.")]
    public Controller robotController;

    [Tooltip("Seconds between samples. 0 = every frame.")]
    public float sampleInterval = 0.1f;

    [Tooltip("Minimum change (absolute) required to consider a joint value 'changed' (avoid noise).")]
    public float changeThreshold = 1e-3f;

    // internal caches
    private List<TransformJoint> mechJoints;
    private float[] lastValues;
    private float timer;

    void Start()
    {
        if (robotController == null)
        {
            robotController = FindObjectOfType<Controller>();
        }

        if (robotController == null)
        {
            Debug.LogError("[JointReader] No Controller found in scene. Disabling script.");
            enabled = false;
            return;
        }

        // cache joint list if available
        var robot = robotController.MechanicalGroup?.Robot;
        if (robot == null)
        {
            Debug.LogError("[JointReader] Controller.MechanicalGroup.Robot is null. Disabling script.");
            enabled = false;
            return;
        }

        // Robot.Joints is expected to be List<JointTransform>
        mechJoints = robot.Joints as List<TransformJoint>;
        lastValues = robot.GetJointValues();
    }

    void Update()
    {
        timer += Time.deltaTime;
        if (sampleInterval > 0f && timer < sampleInterval) return;
        timer = 0f;

        var robot = robotController.MechanicalGroup.Robot;
        if (robot == null) return;

        float[] jointValues = robot.GetJointValues();
        if (jointValues == null || jointValues.Length == 0) return;

        // If same length as lastValues, check for meaningful change
        bool significantChange = false;
        if (lastValues != null && lastValues.Length == jointValues.Length)
        {
            for (int i = 0; i < jointValues.Length; ++i)
            {
                if (Mathf.Abs(jointValues[i] - lastValues[i]) > changeThreshold)
                {
                    significantChange = true;
                    break;
                }
            }
        }
        else
        {
            significantChange = true; // shape changed, so we should log
        }

        if (!significantChange) return;

        // Build a single log string
        var sb = new StringBuilder();
        for (int i = 0; i < jointValues.Length; ++i)
        {
            string jname = (mechJoints != null && i < mechJoints.Count) ? mechJoints[i].name : $"Joint{i}";
            float val = jointValues[i];

            // If values are in radians and you want degrees, use:
            // float display = val * Mathf.Rad2Deg;
            // sb.AppendFormat("{0}: {1:F3}°\n", jname, display);

            sb.AppendFormat("{0}: {1:F4}\n", jname, val);
        }

        Debug.Log(sb.ToString());

        // copy into lastValues
        if (lastValues == null || lastValues.Length != jointValues.Length) lastValues = new float[jointValues.Length];
        for (int i = 0; i < jointValues.Length; ++i) lastValues[i] = jointValues[i];
    }
}
