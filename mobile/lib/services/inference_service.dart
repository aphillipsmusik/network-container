import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:flutter/foundation.dart';
import '../models/cluster_node.dart';
import 'discovery_service.dart';

/// Handles model inference, routing requests to the best available node:
///   1. A full-node on the local cluster (WiFi, best quality)
///   2. On-device llama.cpp (offline / cellular fallback)
class InferenceService extends ChangeNotifier {
  final DiscoveryService _discovery;
  final Dio _dio = Dio(BaseOptions(
    connectTimeout: const Duration(seconds: 5),
    receiveTimeout: const Duration(minutes: 5),
  ));

  ClusterNode? _activeNode;
  bool _usingOnDevice = false;
  bool _generating = false;
  String? _lastError;

  InferenceService(this._discovery);

  ClusterNode? get activeNode => _activeNode;
  bool get usingOnDevice => _usingOnDevice;
  bool get generating => _generating;
  String? get lastError => _lastError;

  String get sourceLabel {
    if (_usingOnDevice) return 'On-device model';
    if (_activeNode != null) return 'Cluster: ${_activeNode!.name}';
    return 'No inference source';
  }

  // ── Select best inference node ────────────────────────────────────────────

  /// Pick the best available inference endpoint.
  /// Returns true if a cluster node was selected, false if falling back
  /// to on-device.
  Future<bool> selectBestNode() async {
    final nodes = _discovery.inferenceNodes;

    // Sort by RAM descending (most capable first)
    nodes.sort((a, b) => (b.ramGb ?? 0).compareTo(a.ramGb ?? 0));

    for (final node in nodes) {
      if (await _pingNode(node)) {
        _activeNode = node;
        _usingOnDevice = false;
        notifyListeners();
        debugPrint('[inference] Using cluster node: ${node.name}');
        return true;
      }
    }

    // No cluster node reachable – use on-device
    _activeNode = null;
    _usingOnDevice = true;
    notifyListeners();
    debugPrint('[inference] No cluster reachable – using on-device');
    return false;
  }

  Future<bool> _pingNode(ClusterNode node) async {
    try {
      final r = await _dio.get(
        '${node.inferenceBaseUrl}/health',
        options: Options(sendTimeout: const Duration(seconds: 3)),
      );
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  // ── Chat completion (streaming) ───────────────────────────────────────────

  /// Stream a chat completion response token-by-token.
  /// Yields delta strings as they arrive.
  Stream<String> chatStream(List<Map<String, String>> messages) async* {
    _lastError = null;
    _generating = true;
    notifyListeners();

    try {
      if (_usingOnDevice) {
        yield* _onDeviceStream(messages);
      } else if (_activeNode != null) {
        yield* _clusterStream(_activeNode!, messages);
      } else {
        yield* (await selectBestNode())
            ? _clusterStream(_activeNode!, messages)
            : _onDeviceStream(messages);
      }
    } catch (e) {
      _lastError = e.toString();
      yield '\n\n[Error: $_lastError]';
    } finally {
      _generating = false;
      notifyListeners();
    }
  }

  // ── Cluster streaming ─────────────────────────────────────────────────────

  Stream<String> _clusterStream(
      ClusterNode node, List<Map<String, String>> messages) async* {
    final url = '${node.inferenceBaseUrl}/v1/chat/completions';
    final body = jsonEncode({
      'model': 'local',
      'messages': messages,
      'stream': true,
      'max_tokens': 2048,
    });

    final request = await _dio.post<ResponseBody>(
      url,
      data: body,
      options: Options(
        headers: {'Content-Type': 'application/json'},
        responseType: ResponseType.stream,
      ),
    );

    final stream = request.data!.stream
        .transform(const Utf8Decoder())
        .transform(const LineSplitter());

    await for (final line in stream) {
      if (!line.startsWith('data: ')) continue;
      final data = line.substring(6).trim();
      if (data == '[DONE]') break;

      try {
        final json = jsonDecode(data) as Map<String, dynamic>;
        final delta = json['choices']?[0]?['delta']?['content'] as String?;
        if (delta != null && delta.isNotEmpty) yield delta;
      } catch (_) {}
    }
  }

  // ── On-device inference (llama.cpp via lcpp package) ─────────────────────

  Stream<String> _onDeviceStream(
      List<Map<String, String>> messages) async* {
    // lcpp package wraps llama.cpp for direct on-device inference.
    // The model path is configured in app settings.
    // See: https://pub.dev/packages/lcpp
    try {
      // Example usage with lcpp package:
      //
      // final llama = Llama(modelPath);
      // final prompt = _formatPrompt(messages);
      // yield* llama.generateStream(prompt, maxTokens: 512);
      //
      // For now, yield a placeholder until lcpp is integrated:
      yield 'On-device inference requires a downloaded model. '
          'Go to Settings → Download Model to get a small model (e.g. Phi-3 mini Q4).';
    } catch (e) {
      yield '[On-device error: $e]';
    }
  }

  String _formatPrompt(List<Map<String, String>> messages) {
    final buffer = StringBuffer();
    for (final msg in messages) {
      final role = msg['role'] ?? 'user';
      final content = msg['content'] ?? '';
      if (role == 'system') {
        buffer.writeln('<|system|>\n$content</s>');
      } else if (role == 'user') {
        buffer.writeln('<|user|>\n$content</s>\n<|assistant|>');
      } else {
        buffer.writeln(content);
      }
    }
    return buffer.toString();
  }

  // ── Manual node selection ─────────────────────────────────────────────────

  void useNode(ClusterNode node) {
    _activeNode = node;
    _usingOnDevice = false;
    notifyListeners();
  }

  void useOnDevice() {
    _activeNode = null;
    _usingOnDevice = true;
    notifyListeners();
  }

  @override
  void dispose() {
    _dio.close();
    super.dispose();
  }
}
