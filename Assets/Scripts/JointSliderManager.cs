using Microsoft.MixedReality.Toolkit.UI;
using Preliy.Flange;
using UnityEngine;

public class JointSliderManager : MonoBehaviour
{
    public Controller robotController;
    public JointSliderUI[] jointUIs; // assign 6 prefab instances here
    public Transform cameraTransform; // assign MainCamera here
    private Robot robot;

    void Start()
    {
        // Parent to Camera
        transform.SetParent(cameraTransform);

        transform.localPosition = new Vector3(0f, 0f, 0.4f); // adjust as needed
        transform.localRotation = Quaternion.identity;

        robot = robotController.MechanicalGroup.Robot;
        float[] jointValues = robot.GetJointValues();

        for (int i = 0; i < jointUIs.Length; i++)
        {
            int idx = i;
            var jt = robot.Joints[idx];

            // Clamp joint value to -360..360 to avoid mapping issues
            float clampedJointValue = Mathf.Clamp(jointValues[idx], -360f, 360f);

            // Initialize slider value (normalized 0..1)
            jointUIs[idx].slider.SliderValue = Mathf.InverseLerp(-360f, 360f, clampedJointValue);

            // Set initial label text
            jointUIs[idx].label.text = $"{jt.name}: {clampedJointValue:F0}";

            // Subscribe to slider updates
            jointUIs[idx].slider.OnValueUpdated.AddListener((SliderEventData data) =>
            {
                float sliderValue = data.NewValue; // normalized 0..1
                float jointValue = Mathf.Lerp(-360f, 360f, sliderValue);

                // Update robot joint values
                jointValues[idx] = jointValue;
                robot.Joints.SetJointValues(jointValues);

                // Update label
                jointUIs[idx].label.text = $"{jt.name}: {jointValue:F0}";
            });
        }
    }
}
