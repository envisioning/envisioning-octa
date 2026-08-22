import CoreText
import Foundation

/// Envisioning Octa, registered from the one build in `dist/`.
///
/// A package cannot use `UIAppFonts` — that key only works from an application's
/// Info.plist — so the face registers itself at runtime. Consumers never bundle
/// the file or add a plist entry.
///
/// One variable file carries eighteen faces: nine weights, each in normal and
/// Expanded width. Every named instance ships a PostScript name, so a face can be
/// addressed directly by `EnvisioningOctaFace.medium.postScriptName`.
public enum EnvisioningOcta {
    public enum Face: String, CaseIterable, Sendable {
        case thin = "Thin"
        case extraLight = "ExtraLight"
        case light = "Light"
        case regular = "Regular"
        case medium = "Medium"
        case semiBold = "SemiBold"
        case bold = "Bold"
        case extraBold = "ExtraBold"
        case black = "Black"

        public var postScriptName: String { "EnvisioningOcta-\(rawValue)" }

        /// The Expanded width names itself after the weight — except at Regular,
        /// where the face is simply "Expanded".
        public var expandedPostScriptName: String {
            self == .regular ? "EnvisioningOcta-Expanded" : "EnvisioningOcta-Expanded\(rawValue)"
        }
    }

    /// Idempotent, and safe from any thread. Only the first call does work.
    public static func register() { _ = registered }

    private static let registered: Bool = {
        guard let url = Bundle.module.url(forResource: "EnvisioningOcta-VF", withExtension: "ttf") else {
            assertionFailure("EnvisioningOcta-VF.ttf missing — did ./build.sh run?")
            return false
        }
        var error: Unmanaged<CFError>?
        if CTFontManagerRegisterFontsForURL(url as CFURL, .process, &error) { return true }
        // Another copy of the package having registered it first is not a failure.
        guard let taken = error?.takeRetainedValue() else { return false }
        return CFErrorGetCode(taken) == CTFontManagerError.alreadyRegistered.rawValue
    }()
}
