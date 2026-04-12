package com.llmcluster

import android.content.Intent
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * MainActivity wires up the MethodChannel so Flutter can start/stop the
 * native llama-rpc-server binary bundled in jniLibs/arm64-v8a/.
 */
class MainActivity : FlutterActivity() {

    private val channel = "com.llmcluster/rpc"

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        MethodChannel(
            flutterEngine.dartExecutor.binaryMessenger, channel
        ).setMethodCallHandler { call, result ->
            when (call.method) {
                "start" -> {
                    val port = call.argument<Int>("port") ?: 50052
                    val gpuLayers = call.argument<Int>("gpuLayers") ?: 0
                    val ok = RpcServerManager.start(applicationContext, port, gpuLayers)
                    result.success(ok)
                }
                "stop" -> {
                    RpcServerManager.stop()
                    result.success(null)
                }
                "isRunning" -> result.success(RpcServerManager.isRunning())
                "getStatus" -> result.success(RpcServerManager.getStatus())
                else -> result.notImplemented()
            }
        }
    }
}
