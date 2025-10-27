using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class CanvasToggle : MonoBehaviour
{
    public GameObject canvasManager;
    public void ToggleCanvas()
    {
        bool active = canvasManager.activeSelf;
        canvasManager.SetActive(!active);
    }
}

