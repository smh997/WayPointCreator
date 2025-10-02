using UnityEngine;

public class RelativePosition : MonoBehaviour
{
    [Header("Assign the robot's Transform here")]
    public Transform robotTransform;

    // The relative position of this object with respect to the robot (UR10 convention)
    public Vector3 relativePositionUR;

    void Update()
    {
        if (robotTransform != null)
        {
            // Get object position in robot's local frame (Unity coords)
            Vector3 localPosUnity = robotTransform.InverseTransformPoint(transform.position);

            // Convert Unity coordinates → UR10 coordinates
            // Unity: (X right, Y up, Z forward)
            // UR10 : (X right, Y forward, Z up)
            relativePositionUR = new Vector3(
                -localPosUnity.x,   // same
                -localPosUnity.z,   // Unity Z → UR Y
                localPosUnity.y    // Unity Y → UR Z
            );

            Debug.Log("Relative Position (UR coords): " + relativePositionUR);
        }
    }
}
