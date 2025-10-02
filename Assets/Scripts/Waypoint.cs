using UnityEngine;
using TMPro;

public class Waypoint : MonoBehaviour
{
    public int OrderIndex; // The order in the sequence
    public TextMeshProUGUI orderText;

    // Robot TCP state (position + rotation)
    public Vector3 tcpPosition;
    public Quaternion tcpRotation;

    void Awake()
    {
        orderText =  GetComponentInChildren<TextMeshProUGUI>();
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
}
