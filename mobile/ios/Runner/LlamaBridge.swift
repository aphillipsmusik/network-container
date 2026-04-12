import Flutter
import Foundation

/**
 * LlamaBridge – Flutter MethodChannel handler for iOS.
 *
 * Manages the llama-rpc-server process compiled as a static library
 * and linked into the iOS app bundle.
 *
 * On iOS, arbitrary executables cannot be spawned as subprocesses.
 * Instead, the RPC server is compiled as a C library and called
 * directly via its C API from Swift.
 *
 * Build instructions: mobile/native/build_ios.sh
 *
 * The llama.cpp RPC server exposes:
 *   int llama_rpc_server_start(const char* host, int port, int n_gpu_layers);
 *   void llama_rpc_server_stop(void);
 *   int  llama_rpc_server_is_running(void);
 */

// C function declarations (linked from llama_rpc.a)
@_silgen_name("llama_rpc_server_start")
func llama_rpc_server_start(_ host: UnsafePointer<CChar>, _ port: Int32, _ gpuLayers: Int32) -> Int32

@_silgen_name("llama_rpc_server_stop")
func llama_rpc_server_stop()

@_silgen_name("llama_rpc_server_is_running")
func llama_rpc_server_is_running() -> Int32

@objc class LlamaBridge: NSObject, FlutterPlugin {

    static func register(with registrar: FlutterPluginRegistrar) {
        let channel = FlutterMethodChannel(
            name: "com.llmcluster/rpc",
            binaryMessenger: registrar.messenger()
        )
        let instance = LlamaBridge()
        registrar.addMethodCallDelegate(instance, channel: channel)
    }

    func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
        switch call.method {
        case "start":
            let args = call.arguments as? [String: Any] ?? [:]
            let port = args["port"] as? Int32 ?? 50052
            let gpuLayers = args["gpuLayers"] as? Int32 ?? 0
            let ok = llama_rpc_server_start("0.0.0.0", port, gpuLayers)
            result(ok == 0)

        case "stop":
            llama_rpc_server_stop()
            result(nil)

        case "isRunning":
            result(llama_rpc_server_is_running() != 0)

        case "getStatus":
            result([
                "running": llama_rpc_server_is_running() != 0,
                "platform": "ios",
            ])

        default:
            result(FlutterMethodNotImplemented)
        }
    }
}
