using UnityEngine;

public class RobotController : MonoBehaviour
{
    public float moveSpeed = 0.1f;
    public float rotateSpeed = 30f;

    [Header("Movement Buttons")]
    public HoldButton xPlusButton;
    public HoldButton xMinusButton;
    public HoldButton yPlusButton;
    public HoldButton yMinusButton;
    public HoldButton zPlusButton;
    public HoldButton zMinusButton;

    [Header("Rotation Buttons")]
    public HoldButton yRotatePlusButton;
    public HoldButton yRotateMinusButton;

    void Update()
    {
        Vector3 move = Vector3.zero;

        // Movement
        if (xPlusButton.isHeld) move += Vector3.right;
        if (xMinusButton.isHeld) move += Vector3.left;
        if (yPlusButton.isHeld) move += Vector3.up;
        if (yMinusButton.isHeld) move += Vector3.down;
        if (zPlusButton.isHeld) move += Vector3.forward;
        if (zMinusButton.isHeld) move += Vector3.back;

        transform.position += move * moveSpeed * Time.deltaTime;

        // Rotation around Y
        if (yRotatePlusButton.isHeld)
            transform.Rotate(Vector3.up * rotateSpeed * Time.deltaTime, Space.World);

        if (yRotateMinusButton.isHeld)
            transform.Rotate(Vector3.down * rotateSpeed * Time.deltaTime, Space.World);
    }
}
