import 'dart:async';
import 'dart:io';
import 'package:flutter/foundation.dart';
import 'package:nsd/nsd.dart';
import '../models/cluster_node.dart';

const _serviceType = '_llama-rpc._tcp';

/// Discovers LLM Cluster nodes on the local network via mDNS,
/// and registers this device as a worker node when active.
class DiscoveryService extends ChangeNotifier {
  final Map<String, ClusterNode> _nodes = {};
  Discovery? _discovery;
  Registration? _registration;

  List<ClusterNode> get nodes => _nodes.values
      .where((n) => !n.isStale)
      .toList()
    ..sort((a, b) => a.name.compareTo(b.name));

  List<ClusterNode> get inferenceNodes =>
      nodes.where((n) => n.fullNode && n.inferencePort != null).toList();

  // ── Browse ────────────────────────────────────────────────────────────────

  Future<void> startBrowsing() async {
    _discovery = await startDiscovery(_serviceType);
    _discovery!.addServiceListener((service, status) {
      if (status == ServiceStatus.found) {
        _onServiceFound(service);
      } else if (status == ServiceStatus.lost) {
        _onServiceLost(service);
      }
    });
    debugPrint('[discovery] Browsing for $_serviceType');

    // Prune stale nodes every 30 seconds
    Timer.periodic(const Duration(seconds: 30), (_) {
      final stale = _nodes.keys
          .where((k) => _nodes[k]!.isStale)
          .toList();
      for (final k in stale) {
        _nodes.remove(k);
      }
      if (stale.isNotEmpty) notifyListeners();
    });
  }

  Future<void> stopBrowsing() async {
    await _discovery?.stop();
    _discovery = null;
  }

  void _onServiceFound(Service service) {
    final host = service.host ?? '';
    final port = service.port ?? 50052;
    final txt = <String, String>{};
    service.attributes?.forEach((k, v) {
      if (v != null) txt[k] = String.fromCharCodes(v);
    });

    // Resolve IP from hostname if needed
    _resolveAndAdd(service.name ?? host, host, port, txt);
  }

  Future<void> _resolveAndAdd(
    String name, String host, int port, Map<String, String> txt) async {
    String ip = host;
    if (!RegExp(r'^\d+\.\d+\.\d+\.\d+$').hasMatch(host)) {
      try {
        final addresses = await InternetAddress.lookup(host);
        if (addresses.isNotEmpty) ip = addresses.first.address;
      } catch (_) {}
    }
    final node = ClusterNode.fromMdnsTxt(name, ip, port, txt);
    _nodes[node.name] = node;
    debugPrint('[discovery] Found: ${node.name} @ ${node.rpcEndpoint}'
        '${node.fullNode ? " [full-node :${node.inferencePort}]" : ""}');
    notifyListeners();
  }

  void _onServiceLost(Service service) {
    final name = service.name ?? '';
    _nodes.removeWhere((k, _) => k == name || k.contains(name));
    debugPrint('[discovery] Lost: $name');
    notifyListeners();
  }

  // ── Register this device as a worker ─────────────────────────────────────

  Future<void> register({
    required String nodeName,
    required int rpcPort,
    required double ramGb,
    bool fullNode = false,
    int? inferencePort,
    int gpuLayers = 0,
  }) async {
    final platform = Platform.isAndroid ? 'android' : 'ios';
    final attrs = <String, Uint8List>{
      'node_name':      Uint8List.fromList(nodeName.codeUnits),
      'rpc_port':       Uint8List.fromList(rpcPort.toString().codeUnits),
      'ram_gb':         Uint8List.fromList(ramGb.toStringAsFixed(1).codeUnits),
      'gpu_layers':     Uint8List.fromList(gpuLayers.toString().codeUnits),
      'full_node':      Uint8List.fromList((fullNode ? 'true' : 'false').codeUnits),
      'platform':       Uint8List.fromList(platform.codeUnits),
    };
    if (inferencePort != null) {
      attrs['inference_port'] =
          Uint8List.fromList(inferencePort.toString().codeUnits);
    }

    _registration = await registerService(Service(
      name: nodeName,
      type: _serviceType,
      port: rpcPort,
      attributes: attrs,
    ));
    debugPrint('[discovery] Registered as $nodeName on port $rpcPort');
  }

  Future<void> unregister() async {
    if (_registration != null) {
      await unregisterService(_registration!);
      _registration = null;
      debugPrint('[discovery] Unregistered');
    }
  }
}
