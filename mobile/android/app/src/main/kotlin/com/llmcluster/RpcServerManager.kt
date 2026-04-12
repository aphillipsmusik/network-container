package com.llmcluster

import android.content.Context
import android.util.Log
import java.io.File

/**
 * Manages the llama-rpc-server native process on Android.
 *
 * The binary is bundled at:
 *   app/src/main/jniLibs/arm64-v8a/llama-rpc-server
 *
 * It is extracted to the app's nativeLibraryDir at install time by the
 * Android package manager, making it executable.
 *
 * Build the binary with the NDK build script at:
 *   mobile/native/build_android.sh
 */
object RpcServerManager {
    private const val TAG = "RpcServerManager"
    private const val BINARY_NAME = "llama-rpc-server"

    private var process: Process? = null

    fun start(context: Context, port: Int, gpuLayers: Int): Boolean {
        if (isRunning()) {
            Log.i(TAG, "Already running")
            return true
        }

        // The binary lives in the native library directory after install
        val binary = File(context.applicationInfo.nativeLibraryDir, "lib$BINARY_NAME.so")
        if (!binary.exists()) {
            Log.e(TAG, "Binary not found: ${binary.absolutePath}")
            return false
        }
        binary.setExecutable(true)

        val cmd = arrayOf(
            binary.absolutePath,
            "--host", "0.0.0.0",
            "--port", port.toString(),
        )
        Log.i(TAG, "Starting: ${cmd.joinToString(" ")}")

        return try {
            process = ProcessBuilder(*cmd)
                .redirectErrorStream(true)
                .start()
            // Log stdout in a daemon thread
            Thread {
                process?.inputStream?.bufferedReader()?.forEachLine {
                    Log.d(TAG, it)
                }
            }.also { it.isDaemon = true }.start()
            true
        } catch (e: Exception) {
            Log.e(TAG, "Failed to start: ${e.message}")
            false
        }
    }

    fun stop() {
        process?.destroy()
        process = null
        Log.i(TAG, "Stopped")
    }

    fun isRunning(): Boolean = process?.isAlive == true

    fun getStatus(): Map<String, Any> = mapOf(
        "running" to isRunning(),
        "pid" to (process?.pid() ?: -1),
    )
}
