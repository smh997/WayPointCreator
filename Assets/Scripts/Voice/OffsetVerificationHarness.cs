using UnityEngine;

/// <summary>
/// TEMPORARY. Verifies WaypointManager.TryApplyOffset's UR-frame-to-Unity axis
/// conversion in isolation, before VoiceCommandRouter or NluDebugInput exist to
/// obscure whether a sign error is in the conversion itself or somewhere else in
/// the pipeline. This conversion has a documented history of wrong signs in this
/// codebase (see the dead/commented conversion in OperationsManager.cs).
///
/// Editor-only. Self-bootstraps -- no scene/prefab wiring required.
/// Keys 1/2/3 apply a +5cm offset along UR x/y/z to the LAST placed waypoint.
///
/// Deleted in Task 9 once NluDebugInput covers this same check end-to-end.
/// </summary>
public class OffsetVerificationHarness : MonoBehaviour
{
#if UNITY_EDITOR || DEVELOPMENT_BUILD
    private WaypointManager waypointManager;
    private OperationsManager operationsManager;

    [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
    private static void Bootstrap()
    {
        var go = new GameObject("[OffsetVerificationHarness]");
        go.AddComponent<OffsetVerificationHarness>();
        DontDestroyOnLoad(go);
    }

    private void Start()
    {
        waypointManager = FindObjectOfType<WaypointManager>();
        operationsManager = FindObjectOfType<OperationsManager>();
    }

    private void Update()
    {
        if (waypointManager == null || operationsManager == null || operationsManager.robotBase == null)
            return;

        string axis = null;
        if (Input.GetKeyDown(KeyCode.Alpha1)) axis = "x";
        else if (Input.GetKeyDown(KeyCode.Alpha2)) axis = "y";
        else if (Input.GetKeyDown(KeyCode.Alpha3)) axis = "z";
        if (axis == null) return;

        var result = waypointManager.TryGetWaypointByReference("last", out Waypoint wp);
        if (result != ReferenceResolution.Resolved)
        {
            Debug.LogWarning("[OffsetVerificationHarness] No waypoint to offset -- place one first.");
            return;
        }

        var offsetResult = waypointManager.TryApplyOffset(wp, axis, 0.05f, operationsManager.robotBase);
        Debug.Log($"[OffsetVerificationHarness] axis={axis} offset=+0.05 -> {offsetResult}");
    }
#endif
}
