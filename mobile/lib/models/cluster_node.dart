/// Cluster node model shared across services.
class ClusterNode {
  final String name;
  final String ip;
  final int rpcPort;
  final bool fullNode;
  final int? inferencePort;
  final double? ramGb;
  final String? gpuName;
  final int? gpuVramMb;
  final DateTime lastSeen;
  final String platform; // "linux", "windows", "android", "ios", "macos"

  const ClusterNode({
    required this.name,
    required this.ip,
    required this.rpcPort,
    required this.lastSeen,
    this.fullNode = false,
    this.inferencePort,
    this.ramGb,
    this.gpuName,
    this.gpuVramMb,
    this.platform = "unknown",
  });

  String get rpcEndpoint => "$ip:$rpcPort";

  String get inferenceBaseUrl {
    if (inferencePort != null) return "http://$ip:$inferencePort";
    return "http://$ip:8080";
  }

  bool get isStale =>
      DateTime.now().difference(lastSeen).inSeconds > 90;

  ClusterNode copyWith({DateTime? lastSeen}) => ClusterNode(
        name: name,
        ip: ip,
        rpcPort: rpcPort,
        fullNode: fullNode,
        inferencePort: inferencePort,
        ramGb: ramGb,
        gpuName: gpuName,
        gpuVramMb: gpuVramMb,
        lastSeen: lastSeen ?? this.lastSeen,
        platform: platform,
      );

  factory ClusterNode.fromMdnsTxt(
    String name,
    String ip,
    int port,
    Map<String, String> txt,
  ) {
    return ClusterNode(
      name: txt['node_name'] ?? name,
      ip: ip,
      rpcPort: int.tryParse(txt['rpc_port'] ?? '') ?? port,
      fullNode: txt['full_node'] == 'true',
      inferencePort: int.tryParse(txt['inference_port'] ?? ''),
      ramGb: double.tryParse(txt['ram_gb'] ?? ''),
      gpuName: txt['gpu_name'],
      gpuVramMb: int.tryParse(txt['gpu_vram_mb'] ?? ''),
      platform: txt['platform'] ?? 'unknown',
      lastSeen: DateTime.now(),
    );
  }

  @override
  String toString() => 'ClusterNode($name @ $rpcEndpoint)';
}
