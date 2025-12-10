using UnityEngine;

public class MenuManager : MonoBehaviour
{
    private OperationsManager operationsManager;

    [Header("Canvases")]
    public GameObject mainMenuCanvas;
    public GameObject configureCanvas;
    public GameObject trajectoryCanvas;
    public GameObject previewRunCanvas;

    [Header("Popups")]
    public GameObject configureConfirmPopup;
    public GameObject quitConfirmPopup;
    public GameObject runConfirmPopup;
    public GameObject infoPopup;

    [Header("Optional")]
    public GameObject dimBackground;

    private void Start()
    {
        ShowMainMenu();
    }

    private void Awake()
    {
        // Get the OperationsManager component on the same GameObject
        operationsManager = GetComponent<OperationsManager>();
        if (operationsManager == null)
        {
            Debug.LogError("OperationsManager not found on Manager GameObject!");
        }
    }

    // -----------------------
    // Canvas Management
    // -----------------------
    public void ShowMainMenu()
    {
        SetAllCanvasesInactive();
        mainMenuCanvas.SetActive(true);
    }

    public void ShowConfigureCanvas()
    {
        SetAllCanvasesInactive();
        configureCanvas.SetActive(true);
    }

    public void ShowTrajectoryCanvas()
    {
        SetAllCanvasesInactive();
        trajectoryCanvas.SetActive(true);
    }

    public void ShowPreviewRunCanvas()
    {
        SetAllCanvasesInactive();
        previewRunCanvas.SetActive(true);
    }

    private void SetAllCanvasesInactive()
    {
        mainMenuCanvas.SetActive(false);
        configureCanvas.SetActive(false);
        trajectoryCanvas.SetActive(false);
        previewRunCanvas.SetActive(false);
    }

    // -----------------------
    // Popups
    // -----------------------
    public void ShowConfigureConfirmation()
    {
        dimBackground?.SetActive(true);
        configureConfirmPopup?.SetActive(true);
    }

    public void HideConfigureConfirmation()
    {
        configureConfirmPopup?.SetActive(false);
        dimBackground?.SetActive(false);
    }

    public void ShowQuitConfirmation()
    {
        dimBackground?.SetActive(true);
        quitConfirmPopup?.SetActive(true);
    }

    public void HideQuitConfirmation()
    {
        quitConfirmPopup?.SetActive(false);
        dimBackground?.SetActive(false);
    }

    public void ShowRunConfirmation()
    {
        runConfirmPopup?.SetActive(true);
    }

    public void HideRunConfirmation()
    {
        runConfirmPopup?.SetActive(false);
    }

    public void ShowInfo()
    {
        infoPopup?.SetActive(true);
    }

    public void HideInfo()
    {
        infoPopup?.SetActive(false);
    }

    // -----------------------
    // Button Callbacks
    // -----------------------
    public void OnConfigurePressed()
    {
        ShowConfigureConfirmation();
    }

    public void OnConfigureConfirmed()
    {
        HideConfigureConfirmation();
        ShowConfigureCanvas();
        operationsManager.SetPhase(PlacementPhase.Calibration);
    }

    public void OnConfigureCancelled()
    {
        HideConfigureConfirmation();
    }

    public void OnTrajectoryPressed()
    {
        ShowTrajectoryCanvas();
        operationsManager.SetPhase(PlacementPhase.Waypoint);
        operationsManager.waypointManager.SetMode(WaypointMode.Create);
    }

    public void OnPreviewRunPressed()
    {
        ShowPreviewRunCanvas();
        operationsManager.SetPhase(PlacementPhase.Preview);
    }

    public void OnRunPressed()
    {
        ShowRunConfirmation();
    }

    public void OnRunConfirmed()
    {
        HideRunConfirmation();
        operationsManager.previewAction = PreviewAction.Run;
    }

    public void OnRunCancelled()
    {
        HideRunConfirmation();
    }

    public void OnPreviewPressed()
    {
        operationsManager.previewAction = PreviewAction.Preview;
    }


    public void OnQuitPressed()
    {
        ShowQuitConfirmation();
    }

    public void OnQuitConfirmed()
    {
        Application.Quit();
    }

    public void OnQuitCancelled()
    {
        HideQuitConfirmation();
    }

    public void OnInfoPressed()
    {
        ShowInfo();
    }
    public void OnInfoClosed()
    {
        HideInfo();
    }

    public void OnSubCanvasExit()
    {
        operationsManager.SetPhase(PlacementPhase.Idle);
        operationsManager.waypointManager.SetMode(WaypointMode.Idle);
        operationsManager.previewAction = PreviewAction.Exit;
        ShowMainMenu();
    }
}
