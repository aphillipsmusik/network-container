import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:flutter_background_service/flutter_background_service.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'discovery_service.dart';

const _notifChannelId = 'llm_worker';
const _notifId = 1;

/// Manages the llama-rpc-server process on this device and the
/// background foreground service that keeps it alive.
class WorkerService extends ChangeNotifier {
  bool _running = false;
  bool _registered = false;
  String _status = 'Stopped';
  int _uptime = 0;
  Timer? _uptimeTimer;

  final DiscoveryService _discovery;

  WorkerService(this._discovery);

  bool get running => _running;
  bool get registered => _registered;
  String get status => _status;
  int get uptimeSeconds => _uptime;

  // ── Start / stop ──────────────────────────────────────────────────────────

  Future<void> start({
    required String nodeName,
    required int rpcPort,
    required int gpuLayers,
    required double ramGb,
  }) async {
    if (_running) return;

    _status = 'Starting RPC server…';
    notifyListeners();

    // Start the native RPC server via platform channel
    final ok = await _startNativeRpcServer(rpcPort: rpcPort, gpuLayers: gpuLayers);
    if (!ok) {
      _status = 'Failed to start RPC server';
      notifyListeners();
      return;
    }

    // Start background service to keep process alive
    await _startBackgroundService(nodeName: nodeName, rpcPort: rpcPort);

    // Register on mDNS
    await _discovery.register(
      nodeName: nodeName,
      rpcPort: rpcPort,
      ramGb: ramGb,
      gpuLayers: gpuLayers,
    );
    _registered = true;

    _running = true;
    _status = 'Running – contributing to cluster';
    _startUptimeTimer();
    notifyListeners();

    debugPrint('[worker] Started on port $rpcPort');
  }

  Future<void> stop() async {
    if (!_running) return;

    _status = 'Stopping…';
    notifyListeners();

    await _discovery.unregister();
    _registered = false;

    await _stopNativeRpcServer();
    await FlutterBackgroundService().invoke('stop');

    _uptimeTimer?.cancel();
    _uptimeTimer = null;
    _running = false;
    _uptime = 0;
    _status = 'Stopped';
    notifyListeners();

    debugPrint('[worker] Stopped');
  }

  // ── Native RPC server (platform channel) ─────────────────────────────────

  /// Calls into native (Kotlin/Swift) to launch llama-rpc-server binary.
  Future<bool> _startNativeRpcServer({
    required int rpcPort,
    required int gpuLayers,
  }) async {
    // Platform channel is defined in android/MainActivity.kt and ios/LlamaBridge.swift
    // Returns true if the binary started successfully.
    try {
      // In production this goes via MethodChannel('com.llmcluster/rpc')
      // For now, simulate success
      await Future.delayed(const Duration(milliseconds: 500));
      return true;
    } catch (e) {
      debugPrint('[worker] Native RPC start failed: $e');
      return false;
    }
  }

  Future<void> _stopNativeRpcServer() async {
    try {
      // MethodChannel('com.llmcluster/rpc').invokeMethod('stop')
      await Future.delayed(const Duration(milliseconds: 200));
    } catch (e) {
      debugPrint('[worker] Native RPC stop failed: $e');
    }
  }

  // ── Background service ────────────────────────────────────────────────────

  static Future<void> initBackgroundService() async {
    final service = FlutterBackgroundService();

    // Android foreground service notification
    const AndroidNotificationChannel channel = AndroidNotificationChannel(
      _notifChannelId,
      'LLM Cluster Worker',
      description: 'Keeps the worker node running in the background',
      importance: Importance.low,
    );
    final notifs = FlutterLocalNotificationsPlugin();
    await notifs
        .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);

    await service.configure(
      androidConfiguration: AndroidConfiguration(
        onStart: _onBackgroundStart,
        autoStart: false,
        isForegroundMode: true,
        notificationChannelId: _notifChannelId,
        initialNotificationTitle: 'LLM Cluster Worker',
        initialNotificationContent: 'Starting…',
        foregroundServiceNotificationId: _notifId,
      ),
      iosConfiguration: IosConfiguration(
        autoStart: false,
        onForeground: _onBackgroundStart,
        onBackground: _onIosBackground,
      ),
    );
  }

  Future<void> _startBackgroundService({
    required String nodeName,
    required int rpcPort,
  }) async {
    final service = FlutterBackgroundService();
    await service.startService();
    service.invoke('configure', {
      'nodeName': nodeName,
      'rpcPort': rpcPort,
    });
  }

  void _startUptimeTimer() {
    _uptime = 0;
    _uptimeTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      _uptime++;
      notifyListeners();
    });
  }
}

// ── Background isolate handlers ───────────────────────────────────────────────

@pragma('vm:entry-point')
void _onBackgroundStart(ServiceInstance service) async {
  final notifs = FlutterLocalNotificationsPlugin();

  service.on('configure').listen((data) {
    final nodeName = data?['nodeName'] ?? 'worker';
    final rpcPort = data?['rpcPort'] ?? 50052;

    // Update the persistent notification
    if (service is AndroidServiceInstance) {
      service.setForegroundNotificationInfo(
        title: 'LLM Cluster: $nodeName',
        content: 'Contributing compute on port $rpcPort',
      );
    }
  });

  service.on('stop').listen((_) {
    service.stopSelf();
  });

  // Heartbeat: update notification every 60 seconds
  Timer.periodic(const Duration(seconds: 60), (_) async {
    final prefs = await SharedPreferences.getInstance();
    final uptimeMins = (prefs.getInt('worker_start_epoch') != null)
        ? ((DateTime.now().millisecondsSinceEpoch -
                    prefs.getInt('worker_start_epoch')!) ~/
                60000)
        : 0;

    if (service is AndroidServiceInstance) {
      service.setForegroundNotificationInfo(
        title: 'LLM Cluster Worker',
        content: 'Active – ${uptimeMins}m uptime',
      );
    }
  });
}

@pragma('vm:entry-point')
Future<bool> _onIosBackground(ServiceInstance service) async {
  // iOS background execution is limited – keep-alive via BGProcessingTask
  return true;
}
