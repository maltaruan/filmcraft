// Uso: swift rosto.swift quadro1.png quadro2.png ...
// Imprime, por arquivo, o centro do maior rosto em fração da imagem (x da esquerda, y do alto),
// ou "nenhum". Usa o Vision do macOS (local, sem rede).
import Foundation
import Vision
import AppKit

for path in CommandLine.arguments.dropFirst() {
    guard let img = NSImage(contentsOfFile: path),
          let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
        print("\(path)\terro"); continue
    }
    let req = VNDetectFaceRectanglesRequest()
    do { try VNImageRequestHandler(cgImage: cg, options: [:]).perform([req]) } catch { print("\(path)\terro"); continue }
    let faces = (req.results ?? []).sorted { $0.boundingBox.width * $0.boundingBox.height > $1.boundingBox.width * $1.boundingBox.height }
    guard let f = faces.first else { print("\(path)\tnenhum"); continue }
    let b = f.boundingBox  // origem embaixo à esquerda, normalizado
    print(String(format: "%@\t%.4f\t%.4f\t%.4f", path, b.midX, 1.0 - b.midY, b.height))
}
