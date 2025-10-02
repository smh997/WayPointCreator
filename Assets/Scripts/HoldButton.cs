using UnityEngine;
using UnityEngine.EventSystems;

public class HoldButton : MonoBehaviour
{
    public bool isHeld = false;

    public void OnPressStart()
    {
        isHeld = true;
    }

    public void OnPressEnd()
    {
        isHeld = false;
    }
}
