// Render chosen pages of any PDF (text, vector, or images) to PNG with macOS's own PDFKit. No install needed.
//
//   swiftc -O docs/sources/tools/render_pdf_pages.swift -o /tmp/render
//   /tmp/render book.pdf out_dir 16 17 81        # page numbers are 1-based
//
// Use this when the PDF is a real document (the Candlestick Bible). For an image-only deck, pdf_pages_to_png.py
// gives the picture at its native size; this one rasterises at 1400 px wide.
import Foundation
import PDFKit
import AppKit

let args = CommandLine.arguments
let doc = PDFDocument(url: URL(fileURLWithPath: args[1]))!
for a in args.dropFirst(3) {
    guard let n = Int(a), let page = doc.page(at: n - 1) else { continue }
    let r = page.bounds(for: .mediaBox)
    let scale = 1400.0 / r.width
    let img = page.thumbnail(of: NSSize(width: r.width * scale, height: r.height * scale), for: .mediaBox)
    if let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
       let png = rep.representation(using: .png, properties: [:]) {
        try? png.write(to: URL(fileURLWithPath: "\(args[2])/p\(String(format: "%03d", n)).png"))
    }
}
