using Microsoft.MixedReality.Toolkit.UI;
using TMPro;
using UnityEngine;

public class Waypoint : MonoBehaviour
{
    public int OrderIndex; // The order in the sequence
    public TextMeshProUGUI orderText;

    // Robot TCP state (position + rotation)
    public Vector3 tcpPosition;
    public Quaternion tcpRotation;

    private WaypointManager manager;

    private ObjectManipulator manipulator;

    private Renderer coneRenderer;
    private Renderer sphereRenderer;


    public Material normalMat;   // Yellow
    public Material editMat;     // Light Blue
    public Material deleteMat;   // Red

    void Awake()
    {
        orderText = GetComponentInChildren<TextMeshProUGUI>();
        manager = FindObjectOfType<WaypointManager>();
        coneRenderer = transform.Find("Piece/Cone")?.GetComponent<Renderer>();
        sphereRenderer = transform.Find("Piece/Sphere")?.GetComponent<Renderer>();
        manipulator = GetComponent<ObjectManipulator>();
        if (manipulator != null)
        {
            manipulator.enabled = false; // Disable by default
        }
    }

    public void SetOrder(int index)
    {
        OrderIndex = index;
        if (orderText != null)
            orderText.text = index.ToString();
    }

    public void UpdateState()
    {
        tcpPosition = transform.position;
        tcpRotation = transform.rotation;

    }

    public void setColor()
    {
        Material mat;
        switch (manager.Mode)
        {
            case WaypointMode.Create:
                mat = normalMat;
                break;
            case WaypointMode.Delete:
                mat = deleteMat; 
                break;
            case WaypointMode.Edit: 
                mat = editMat;
                break;
            default:
                mat = normalMat;
                break;
        }
        sphereRenderer.material = mat;
        coneRenderer.material = mat;
        orderText.color = mat.color;
    }

    public void resetColor()
    {
        sphereRenderer.material = normalMat;
        coneRenderer.material = normalMat;
        orderText.color = normalMat.color;
    }

    public void StartEditing()
    {
        if (manipulator != null)
            manipulator.enabled = true;
        setColor();
    }

    public void StopEditing()
    {
        if (manipulator != null)
            manipulator.enabled = false;
        resetColor();
    }


    public void OnHandDelete()
    {
        if (manager != null && manager.Mode == WaypointMode.Delete)
        {
            manager.RemoveWaypoint(this);
        }
    }


}
