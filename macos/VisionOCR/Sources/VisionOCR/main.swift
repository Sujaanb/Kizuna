import Foundation
import Vision
import AppKit

struct Candidate: Codable { let text: String; let confidence: Float }
struct Observation: Codable {
    let text: String
    let confidence: Float
    let bbox: [Double]
    let candidates: [Candidate]
}
struct Response: Codable {
    let languages: [String]
    let japaneseSupported: Bool
    let observations: [Observation]
}
func run() throws {
    let request = VNRecognizeTextRequest()
    request.recognitionLevel = .accurate
    request.usesLanguageCorrection = true
    let supported = try request.supportedRecognitionLanguages()
    let languages = ["ja-JP", "en-US"].filter { supported.contains($0) }
    var observations: [Observation] = []
    if CommandLine.arguments.count > 1 && CommandLine.arguments[1] != "--languages" {
        guard supported.contains("ja-JP") else {
            throw NSError(domain: "VisionOCR", code: 1, userInfo: [NSLocalizedDescriptionKey: "Japanese is not supported by this Vision runtime"])
        }
        request.recognitionLanguages = languages
        let url = URL(fileURLWithPath: CommandLine.arguments[1])
        try VNImageRequestHandler(url: url, options: [:]).perform([request])
        observations = (request.results ?? []).compactMap { observation in
            let choices = observation.topCandidates(3)
            guard let first = choices.first else { return nil }
            let b = observation.boundingBox
            return Observation(text: first.string, confidence: first.confidence,
                bbox: [b.minX, b.minY, b.width, b.height],
                candidates: choices.map { Candidate(text: $0.string, confidence: $0.confidence) })
        }
    }
    let result = Response(languages: languages, japaneseSupported: supported.contains("ja-JP"), observations: observations)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    FileHandle.standardOutput.write(try encoder.encode(result))
}
do { try run() } catch {
    FileHandle.standardError.write(Data("VisionOCR: \(error.localizedDescription)\n".utf8))
    exit(1)
}
