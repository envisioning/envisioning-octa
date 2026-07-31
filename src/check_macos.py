#!/usr/bin/env python3
"""Ask macOS itself whether the fonts are valid, via CoreText.

Registering a font with CTFontManager is the same path Font Book and every
Mac app takes, so a clean pass here means the file will actually install.
"""

import ctypes
import ctypes.util
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FAMILY_NAME = "Envisioning Octa"

cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
ct = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreText"))

cf.CFURLCreateFromFileSystemRepresentation.restype = ctypes.c_void_p
cf.CFURLCreateFromFileSystemRepresentation.argtypes = [
    ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_bool
]
cf.CFArrayGetCount.restype = ctypes.c_long
cf.CFArrayGetCount.argtypes = [ctypes.c_void_p]
cf.CFArrayGetValueAtIndex.restype = ctypes.c_void_p
cf.CFArrayGetValueAtIndex.argtypes = [ctypes.c_void_p, ctypes.c_long]
cf.CFStringGetCString.argtypes = [
    ctypes.c_void_p, ctypes.c_char_p, ctypes.c_long, ctypes.c_uint32
]
cf.CFRelease.argtypes = [ctypes.c_void_p]

ct.CTFontManagerCreateFontDescriptorsFromURL.restype = ctypes.c_void_p
ct.CTFontManagerCreateFontDescriptorsFromURL.argtypes = [ctypes.c_void_p]
ct.CTFontDescriptorCopyAttribute.restype = ctypes.c_void_p
ct.CTFontDescriptorCopyAttribute.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

FAMILY_ATTR = ctypes.c_void_p.in_dll(ct, "kCTFontFamilyNameAttribute")
STYLE_ATTR = ctypes.c_void_p.in_dll(ct, "kCTFontStyleNameAttribute")
PS_ATTR = ctypes.c_void_p.in_dll(ct, "kCTFontNameAttribute")


def cfstr(ref):
    buf = ctypes.create_string_buffer(256)
    cf.CFStringGetCString(ref, buf, 256, 0x08000100)  # kCFStringEncodingUTF8
    return buf.value.decode("utf-8")


def descriptors(path):
    url = cf.CFURLCreateFromFileSystemRepresentation(
        None, path.encode("utf-8"), len(path.encode("utf-8")), False
    )
    if not url:
        return None
    arr = ct.CTFontManagerCreateFontDescriptorsFromURL(url)
    cf.CFRelease(url)
    if not arr:
        return None
    faces = []
    for i in range(cf.CFArrayGetCount(arr)):
        desc = cf.CFArrayGetValueAtIndex(arr, i)
        faces.append(
            tuple(
                cfstr(ct.CTFontDescriptorCopyAttribute(desc, a)) or "<unnamed>"
                for a in (FAMILY_ATTR, STYLE_ATTR, PS_ATTR)
            )
        )
    cf.CFRelease(arr)
    return faces


paths = [os.path.join(ROOT, "dist", "EnvisioningOcta-VF.ttf")] + sorted(
    glob.glob(os.path.join(ROOT, "dist", "static", "*.ttf"))
)

failed = []
for path in paths:
    faces = descriptors(path)
    label = os.path.relpath(path, ROOT)
    if not faces:
        print(f"FAIL  {label}  CoreText rejected the file")
        failed.append(label)
        continue

    families = {f[0] for f in faces}
    if families != {FAMILY_NAME}:
        print(f"FAIL  {label}  unexpected family name(s): {sorted(families)}")
        failed.append(label)
        continue

    styles = ", ".join(f[1] for f in faces)
    print(f"PASS  {label}  {FAMILY_NAME}: {styles}")

print()
if failed:
    print(f"{len(failed)} file(s) rejected by CoreText")
    sys.exit(1)
print(f"macOS accepts all {len(paths)} files")
