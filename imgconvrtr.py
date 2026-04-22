import io
import ctypes
import os
import sys
import subprocess
import tempfile
from ctypes import c_uint8, c_int, c_float, c_size_t, c_uint32, POINTER, Structure
from ctypes.util import find_library
from PIL import Image
import numpy as np

# Maximum file size limit: 200MB
MAX_FILE_SIZE_MB = 200
MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024  # 200MB in bytes

# SVG support will be lazy-loaded to avoid import errors if dependencies aren't available
_svg_available = None  # Will be checked on first use

# Try importing pillow-avif-plugin for AVIF support
try:
    import pillow_avif
    _avif_plugin_available = True
except ImportError:
    _avif_plugin_available = False

# Store diagnostic information
_libwebp_load_errors = []
_libavif_load_errors = []
_compression_tools = {}

def _try_load_libwebp(path):
    """Try to load libwebp from a specific path."""
    try:
        lib = ctypes.CDLL(path)
        _libwebp_load_errors.append(f"✅ Successfully loaded: {path}")
        return lib
    except OSError as e:
        _libwebp_load_errors.append(f"❌ Failed to load {path}: {e}")
        return None
    except Exception as e:
        _libwebp_load_errors.append(f"❌ Error loading {path}: {e}")
        return None

# Try to load libwebp library
libwebp = None

try:
    # First, try using find_library (works on most systems)
    found_lib = find_library('webp')
    if found_lib:
        libwebp = _try_load_libwebp(found_lib)
    
    # Also try 'libwebp' name
    if not libwebp:
        found_lib = find_library('libwebp')
        if found_lib:
            libwebp = _try_load_libwebp(found_lib)
    
    # If find_library didn't work, try manual paths
    if not libwebp:
        if hasattr(ctypes, 'windll'):
            # Windows - try multiple locations
            search_paths = [
                'libwebp.dll',  # System PATH
                'webp.dll',     # Alternative name
                os.path.join(os.path.dirname(__file__), 'libwebp.dll'),  # Same directory as script
                os.path.join(os.path.dirname(__file__), 'webp.dll'),
                os.path.join(sys.exec_prefix, 'libwebp.dll'),  # Python installation directory
                'C:\\Windows\\System32\\libwebp.dll',  # System32
                'C:\\Program Files\\libwebp\\bin\\libwebp.dll',  # Common installation path
            ]
            
            for path in search_paths:
                libwebp = _try_load_libwebp(path)
                if libwebp:
                    break
        else:
            # Linux/Mac
            search_paths = [
                'libwebp.so',      # System PATH
                'libwebp.so.7',    # Versioned
                'libwebp.so.8',
                'libwebp.dylib',   # macOS
                os.path.join(os.path.dirname(__file__), 'libwebp.so'),
                '/usr/lib/libwebp.so',
                '/usr/local/lib/libwebp.so',
                '/opt/homebrew/lib/libwebp.dylib',  # Homebrew on Apple Silicon
            ]
            
            for path in search_paths:
                libwebp = _try_load_libwebp(path)
                if libwebp:
                    break
except Exception as e:
    _libwebp_load_errors.append(f"❌ Unexpected error: {e}")
    libwebp = None

# Define WebP function signatures if libwebp is available
if libwebp:
    # WebPEncodeRGBA signature
    libwebp.WebPEncodeRGBA.argtypes = [
        POINTER(c_uint8),  # rgba
        c_int,             # width
        c_int,             # height
        c_int,             # stride
        c_float,           # quality_factor
        POINTER(POINTER(c_uint8))  # output
    ]
    libwebp.WebPEncodeRGBA.restype = c_size_t
    
    # WebPEncodeRGB signature
    libwebp.WebPEncodeRGB.argtypes = [
        POINTER(c_uint8),  # rgb
        c_int,             # width
        c_int,             # height
        c_int,             # stride
        c_float,           # quality_factor
        POINTER(POINTER(c_uint8))  # output
    ]
    libwebp.WebPEncodeRGB.restype = c_size_t
    
    # WebPEncodeLosslessRGBA signature
    libwebp.WebPEncodeLosslessRGBA.argtypes = [
        POINTER(c_uint8),  # rgba
        c_int,             # width
        c_int,             # height
        c_int,             # stride
        POINTER(POINTER(c_uint8))  # output
    ]
    libwebp.WebPEncodeLosslessRGBA.restype = c_size_t
    
    # WebPDecodeRGBA signature
    libwebp.WebPDecodeRGBA.argtypes = [
        POINTER(c_uint8),  # data
        c_size_t,          # data_size
        POINTER(c_int),    # width
        POINTER(c_int)     # height
    ]
    libwebp.WebPDecodeRGBA.restype = POINTER(c_uint8)
    
    # WebPDecodeRGB signature
    libwebp.WebPDecodeRGB.argtypes = [
        POINTER(c_uint8),  # data
        c_size_t,          # data_size
        POINTER(c_int),    # width
        POINTER(c_int)     # height
    ]
    libwebp.WebPDecodeRGB.restype = POINTER(c_uint8)
    
    # WebPFree signature for freeing memory
    libwebp.WebPFree.argtypes = [ctypes.c_void_p]
    libwebp.WebPFree.restype = None
    
    # WebPGetInfo signature
    libwebp.WebPGetInfo.argtypes = [
        POINTER(c_uint8),  # data
        c_size_t,          # data_size
        POINTER(c_int),    # width
        POINTER(c_int)     # height
    ]
    libwebp.WebPGetInfo.restype = c_int


# Try to load libavif library for AVIF support
libavif = None

try:
    # Try using find_library
    found_lib = find_library('avif')
    if found_lib:
        libavif = _try_load_libwebp(found_lib)
        if libavif:
            _libavif_load_errors.append(f"✅ Successfully loaded: {found_lib}")
    
    # Try 'libavif' name
    if not libavif:
        found_lib = find_library('libavif')
        if found_lib:
            libavif = _try_load_libwebp(found_lib)
            if libavif:
                _libavif_load_errors.append(f"✅ Successfully loaded: {found_lib}")
    
    # Manual paths if find_library didn't work
    if not libavif:
        if hasattr(ctypes, 'windll'):
            # Windows
            search_paths = [
                'libavif.dll',
                'avif.dll',
                os.path.join(os.path.dirname(__file__), 'libavif.dll'),
                os.path.join(os.path.dirname(__file__), 'avif.dll'),
                'C:\\Windows\\System32\\libavif.dll',
            ]
            
            for path in search_paths:
                try:
                    libavif = ctypes.CDLL(path)
                    _libavif_load_errors.append(f"✅ Successfully loaded: {path}")
                    break
                except:
                    _libavif_load_errors.append(f"❌ Failed to load {path}")
        else:
            # Linux/Mac
            search_paths = [
                'libavif.so',
                'libavif.so.15',
                'libavif.so.16',
                'libavif.dylib',
                os.path.join(os.path.dirname(__file__), 'libavif.so'),
                '/usr/lib/libavif.so',
                '/usr/local/lib/libavif.so',
                '/opt/homebrew/lib/libavif.dylib',
            ]
            
            for path in search_paths:
                try:
                    libavif = ctypes.CDLL(path)
                    _libavif_load_errors.append(f"✅ Successfully loaded: {path}")
                    break
                except:
                    _libavif_load_errors.append(f"❌ Failed to load {path}")
except Exception as e:
    _libavif_load_errors.append(f"❌ Unexpected error: {e}")
    libavif = None


# Detect compression tools
def _check_tool_available(tool_name):
    """Check if a compression tool is available in PATH."""
    try:
        result = subprocess.run([tool_name, '--version'], 
                              capture_output=True, 
                              timeout=5)
        return result.returncode == 0
    except:
        return False

# Check for compression tools
_compression_tools['mozjpeg'] = _check_tool_available('cjpeg') or _check_tool_available('mozjpeg')
_compression_tools['oxipng'] = _check_tool_available('oxipng')
_compression_tools['optipng'] = _check_tool_available('optipng')


def is_libwebp_available():
    """Check if libwebp library is available."""
    return libwebp is not None


def get_libwebp_diagnostics():
    """Get diagnostic information about libwebp loading attempts."""
    return _libwebp_load_errors.copy()


def is_libavif_available():
    """Check if libavif library is available."""
    return libavif is not None or _avif_plugin_available


def get_libavif_diagnostics():
    """Get diagnostic information about libavif loading attempts."""
    diag = _libavif_load_errors.copy()
    if _avif_plugin_available:
        diag.append("✅ pillow-avif-plugin is available")
    return diag


def get_compression_tools():
    """Get dictionary of available compression tools."""
    return _compression_tools.copy()


def _check_svg_support():
    """Lazy-load SVG dependencies to avoid import errors at module level."""
    global _svg_available
    if _svg_available is None:
        try:
            # Test if dependencies are available without importing renderPM
            from svglib.svglib import svg2rlg
            from reportlab.pdfgen import canvas
            from pdf2image import convert_from_bytes
            _svg_available = True
        except (ImportError, OSError):
            # OSError can occur if pdf2image can't find poppler
            _svg_available = False
    return _svg_available


def rasterize_svg(svg_data, width=None, height=None, dpi=96):
    """
    Rasterize SVG data to a PIL Image using svglib and reportlab PDF rendering.
    Uses PDF as an intermediate format to avoid Cairo dependency.
    Requires pdf2image for PDF to image conversion.
    
    Args:
        svg_data: bytes or string of SVG data
        width: target width in pixels (None for auto)
        height: target height in pixels (None for auto)
        dpi: resolution for rasterization (default 96)
    
    Returns:
        PIL.Image: Rasterized image
    """
    if not _check_svg_support():
        raise RuntimeError(
            "SVG support requires svglib, reportlab, and pdf2image. Install with: pip install svglib reportlab pdf2image\n"
            "Note: pdf2image also requires poppler. See README for installation instructions."
        )
    
    # Import here to avoid import errors at module level
    from svglib.svglib import svg2rlg
    from reportlab.pdfgen import canvas
    
    # Convert to bytes and remove XML encoding declaration (svglib requirement)
    if isinstance(svg_data, str):
        svg_string = svg_data
    else:
        svg_string = svg_data.decode('utf-8', errors='ignore')
    
    # Remove XML encoding declaration and DOCTYPE if present (svglib doesn't support them)
    svg_string = svg_string.strip()
    
    # Remove XML declaration
    if svg_string.startswith('<?xml'):
        end_xml = svg_string.find('?>')
        if end_xml != -1:
            svg_string = svg_string[end_xml + 2:].strip()
    
    # Remove DOCTYPE declaration if present
    if svg_string.startswith('<!DOCTYPE'):
        end_doctype = svg_string.find('>')
        if end_doctype != -1:
            svg_string = svg_string[end_doctype + 1:].strip()
    
    # Convert back to bytes for svglib (it requires bytes input)
    svg_bytes = svg_string.encode('utf-8')
    
    # Create a BytesIO object for svglib
    svg_io = io.BytesIO(svg_bytes)
    
    try:
        # Convert SVG to ReportLab drawing
        drawing = svg2rlg(svg_io)
        
        if drawing is None:
            raise RuntimeError("Failed to parse SVG file")
        
        # Scale if dimensions specified
        if width or height:
            scale_x = scale_y = 1.0
            if width and drawing.width:
                scale_x = width / drawing.width
            if height and drawing.height:
                scale_y = height / drawing.height
            if width and height:
                # Use the smaller scale to maintain aspect ratio
                scale = min(scale_x, scale_y)
            else:
                scale = scale_x if width else scale_y
            drawing.width *= scale
            drawing.height *= scale
            drawing.scale(scale, scale)
        
        # Render to PDF bytes using canvas (this doesn't require Cairo)
        page_width = drawing.width if drawing.width else 800
        page_height = drawing.height if drawing.height else 600
        pdf_buffer = io.BytesIO()
        c = canvas.Canvas(pdf_buffer, pagesize=(page_width, page_height))
        drawing.drawOn(c, 0, 0)
        c.save()
        pdf_bytes = pdf_buffer.getvalue()
        pdf_buffer.close()
        
        # Convert PDF to image using pdf2image
        try:
            from pdf2image import convert_from_bytes
            images = convert_from_bytes(pdf_bytes, dpi=dpi)
            if images:
                return images[0]  # Return first page
            else:
                raise RuntimeError("PDF conversion produced no images")
        except ImportError:
            raise RuntimeError(
                "PDF to image conversion requires pdf2image. Install with: pip install pdf2image\n"
                "Note: On Windows, you may also need poppler-utils. See installation instructions in README."
            )
        
    except Exception as e:
        raise RuntimeError(f"SVG rasterization failed: {e}")


def optimize_png(png_data, tool='auto', strip_mode='safe'):
    """
    Optimize PNG using OxiPNG or OptiPNG.
    
    Args:
        png_data: bytes of PNG data
        tool: 'oxipng', 'optipng', or 'auto' (picks best available)
    
    Returns:
        bytes: optimized PNG data
    """
    if tool == 'auto':
        tool = 'oxipng' if _compression_tools.get('oxipng') else 'optipng'
    
    if not _compression_tools.get(tool):
        return png_data  # Return original if tool not available
    
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.png') as tmp_in:
            tmp_in.write(png_data)
            tmp_in_path = tmp_in.name
        
        strip_value = 'safe' if strip_mode not in {'none', 'safe', 'all'} else strip_mode

        if tool == 'oxipng':
            subprocess.run([tool, '--opt', 'max', '--strip', strip_value, tmp_in_path],
                         check=True, capture_output=True)
        elif tool == 'optipng':
            optipng_strip = 'all' if strip_value == 'all' else 'safe'
            subprocess.run([tool, '-o7', '-strip', optipng_strip, tmp_in_path], check=True, capture_output=True)
        
        with open(tmp_in_path, 'rb') as f:
            optimized_data = f.read()
        
        os.unlink(tmp_in_path)
        return optimized_data
    except Exception as e:
        if 'tmp_in_path' in locals():
            try:
                os.unlink(tmp_in_path)
            except:
                pass
        return png_data  # Return original on error


def optimize_jpeg_mozjpeg(rgb_data, width, height, quality=50):
    """
    Optimize JPEG using MozJPEG.
    
    Args:
        rgb_data: bytes of RGB data
        width: image width
        height: image height
        quality: quality factor (0-100)
    
    Returns:
        bytes: optimized JPEG data
    """
    if not _compression_tools.get('mozjpeg'):
        return None  # Indicate MozJPEG not available
    
    try:
        # Create temporary PPM file (MozJPEG input)
        with tempfile.NamedTemporaryFile(delete=False, suffix='.ppm', mode='wb') as tmp_in:
            # Write PPM header
            header = f'P6\n{width} {height}\n255\n'.encode('ascii')
            tmp_in.write(header)
            tmp_in.write(rgb_data)
            tmp_in_path = tmp_in.name
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.jpg') as tmp_out:
            tmp_out_path = tmp_out.name
        
        # Run cjpeg (MozJPEG)
        cmd = ['cjpeg', '-quality', str(quality), '-outfile', tmp_out_path, tmp_in_path]
        subprocess.run(cmd, check=True, capture_output=True)
        
        with open(tmp_out_path, 'rb') as f:
            optimized_data = f.read()
        
        os.unlink(tmp_in_path)
        os.unlink(tmp_out_path)
        return optimized_data
    except Exception as e:
        for path in [locals().get('tmp_in_path'), locals().get('tmp_out_path')]:
            if path:
                try:
                    os.unlink(path)
                except:
                    pass
        return None


def _has_alpha_channel(img):
    """Return True when image mode has alpha information."""
    if img.mode in ('RGBA', 'LA'):
        return True
    if img.mode == 'P':
        return 'transparency' in img.info
    return False


def _subsampling_to_pillow_value(subsampling):
    """Map user-friendly subsampling string to Pillow integer value."""
    mapping = {
        '4:4:4': 0,
        '4:2:2': 1,
        '4:2:0': 2,
    }
    return mapping.get(subsampling, subsampling)


def _detect_webp_signature(image_data):
    """Detect WebP by RIFF/WebP signature without decoding."""
    if not isinstance(image_data, (bytes, bytearray)) or len(image_data) < 12:
        return False
    return image_data[0:4] == b'RIFF' and image_data[8:12] == b'WEBP'


def _build_metadata_kwargs(output_format_lower, metadata, preserve_icc=True, preserve_exif=False, preserve_xmp=False):
    """Build format-specific metadata kwargs for Pillow save."""
    metadata_kwargs = {}
    if preserve_icc and metadata.get('icc_profile'):
        metadata_kwargs['icc_profile'] = metadata['icc_profile']
    if preserve_exif and metadata.get('exif') and output_format_lower in {'jpeg', 'jpg', 'jfif', 'webp', 'png'}:
        metadata_kwargs['exif'] = metadata['exif']
    if preserve_xmp and metadata.get('xmp') and output_format_lower in {'webp', 'png'}:
        metadata_kwargs['xmp'] = metadata['xmp']
    return metadata_kwargs


def _save_with_fallback(img, output_img, save_kwargs):
    """Save with graceful fallback when some Pillow options are unsupported."""
    try:
        img.save(output_img, **save_kwargs)
        return
    except TypeError:
        fallback_kwargs = save_kwargs.copy()
        for key in ('xmp', 'exif', 'icc_profile', 'subsampling', 'speed', 'exact', 'alpha_quality', 'method'):
            fallback_kwargs.pop(key, None)
        img.save(output_img, **fallback_kwargs)


def encode_to_webp(rgba_data, width, height, quality_factor=80.0, lossless=False):
    """
    Encode RGBA image data to WebP using libwebp API.
    
    Args:
        rgba_data: bytes or numpy array of RGBA data
        width: image width
        height: image height
        quality_factor: quality factor (0-100) for lossy encoding
        lossless: if True, use lossless encoding
    
    Returns:
        bytes: WebP encoded data
    """
    if not libwebp:
        raise RuntimeError("libwebp library not found. Please install libwebp.")
    
    # Convert to bytes if numpy array
    if isinstance(rgba_data, np.ndarray):
        rgba_data = rgba_data.tobytes()
    
    # Create ctypes array
    rgba_array = (c_uint8 * len(rgba_data)).from_buffer_copy(rgba_data)
    stride = width * 4  # RGBA = 4 bytes per pixel
    
    # Create output pointer
    output_ptr = POINTER(c_uint8)()
    
    if lossless:
        # Use lossless encoding
        size = libwebp.WebPEncodeLosslessRGBA(
            rgba_array, width, height, stride, ctypes.byref(output_ptr)
        )
    else:
        # Use lossy encoding
        size = libwebp.WebPEncodeRGBA(
            rgba_array, width, height, stride, quality_factor, ctypes.byref(output_ptr)
        )
    
    if size == 0 or output_ptr is None:
        raise RuntimeError("WebP encoding failed")
    
    # Copy the encoded data
    webp_data = bytes(ctypes.string_at(output_ptr, size))
    
    # Free the memory allocated by libwebp
    libwebp.WebPFree(output_ptr)
    
    return webp_data


def decode_from_webp(webp_data):
    """
    Decode WebP image data to RGBA using libwebp API.
    
    Args:
        webp_data: bytes of WebP encoded data
    
    Returns:
        tuple: (rgba_data, width, height) where rgba_data is bytes
    """
    if not libwebp:
        raise RuntimeError("libwebp library not found. Please install libwebp.")
    
    # Create ctypes array from WebP data
    webp_array = (c_uint8 * len(webp_data)).from_buffer_copy(webp_data)
    
    # Get image info first
    width = c_int()
    height = c_int()
    if libwebp.WebPGetInfo(webp_array, len(webp_data), ctypes.byref(width), ctypes.byref(height)) == 0:
        raise RuntimeError("Invalid WebP data")
    
    width_val = width.value
    height_val = height.value
    
    # Decode RGBA
    rgba_ptr = libwebp.WebPDecodeRGBA(webp_array, len(webp_data), ctypes.byref(width), ctypes.byref(height))
    
    if rgba_ptr is None:
        raise RuntimeError("WebP decoding failed")
    
    # Calculate size and copy data
    rgba_size = width_val * height_val * 4
    rgba_data = bytes(ctypes.string_at(rgba_ptr, rgba_size))
    
    # Free the memory allocated by libwebp
    libwebp.WebPFree(rgba_ptr)
    
    return rgba_data, width_val, height_val


def convert_img_format(
    image_file,
    output_format,
    quality=82,
    lossless=False,
    optimize=False,
    preserve_icc=True,
    preserve_exif=False,
    preserve_xmp=False,
    advanced_options=None,
    jpeg_background=(255, 255, 255),
):
    """
    Convert image format with support for AVIF, WebP, SVG, and optimization.
    
    Args:
        image_file: file-like object or bytes
        output_format: target format (avif, webp, png, jpeg, jpg, jfif, bmp)
        quality: quality factor for lossy formats (0-100)
        lossless: if True, use lossless encoding for WebP/AVIF
        optimize: if True, use compression tools (MozJPEG, OxiPNG, etc.)
    
    Returns:
        BytesIO: converted image data
    """
    output_format_lower = output_format.lower()
    
    # Handle different input types - always read bytes first for reliability
    image_data = None
    
    # Read image data first
    if hasattr(image_file, 'read'):
        # File-like object (e.g., Streamlit UploadedFile)
        try:
            image_file.seek(0)  # Reset to beginning
            
            # Check file size before reading if size attribute is available
            if hasattr(image_file, 'size') and image_file.size > MAX_FILE_SIZE_BYTES:
                raise ValueError(
                    f"File size ({image_file.size / (1024 * 1024):.1f}MB) exceeds the maximum limit of {MAX_FILE_SIZE_MB}MB. "
                    f"Please use a smaller file."
                )
            
            image_data = image_file.read()
            if not image_data:
                raise ValueError("Empty file or could not read file data")
        except ValueError:
            # Re-raise ValueError (including our file size error)
            raise
        except Exception as e:
            raise ValueError(f"Could not read image file: {e}")
    else:
        # Assume it's bytes
        image_data = image_file
        if not image_data:
            raise ValueError("Empty image data provided")
    
    # Check file size after reading (defense in depth)
    if len(image_data) > MAX_FILE_SIZE_BYTES:
        file_size_mb = len(image_data) / (1024 * 1024)
        raise ValueError(
            f"File size ({file_size_mb:.1f}MB) exceeds the maximum limit of {MAX_FILE_SIZE_MB}MB. "
            f"Please use a smaller file."
        )
    
    # Check if input is SVG and rasterize it first
    is_svg = False
    if isinstance(image_data, bytes):
        # Check for SVG magic bytes or XML declaration
        try:
            image_data_str = image_data[:200].decode('utf-8', errors='ignore').strip()
            if image_data_str.startswith('<?xml') or image_data_str.startswith('<svg'):
                is_svg = True
        except:
            pass
        # Also check filename if available
        if not is_svg and hasattr(image_file, 'name') and image_file.name:
            if image_file.name.lower().endswith('.svg'):
                is_svg = True
    
    # Rasterize SVG if needed
    input_format = None
    if is_svg:
        try:
            img = rasterize_svg(image_data)
            input_format = 'SVG'
        except Exception as e:
            raise RuntimeError(f"SVG rasterization failed: {e}")
    else:
        # Now open with PIL using the bytes data
        try:
            img = Image.open(io.BytesIO(image_data))
            input_format = (img.format or '').upper()
        except Exception as e:
            raise ValueError(f"Could not identify image format. The file may be corrupted or in an unsupported format: {e}")

    # Keep source metadata for optional preservation.
    metadata = {
        'icc_profile': img.info.get('icc_profile'),
        'exif': img.info.get('exif'),
        'xmp': img.info.get('xmp'),
    }

    if not input_format and _detect_webp_signature(image_data):
        input_format = 'WEBP'

    # Handle WebP input using libwebp API before any mode conversion.
    if input_format == 'WEBP' and libwebp:
        try:
            decoded_rgba_data, width, height = decode_from_webp(image_data)
            img = Image.frombytes('RGBA', (width, height), decoded_rgba_data)
        except Exception as e:
            print(f"libwebp decoding failed, using PIL fallback: {e}")

    advanced_options = advanced_options or {}
    
    # Handle AVIF output
    if output_format_lower == 'avif':
        output_img = io.BytesIO()
        try:
            # Try using pillow-avif-plugin or Pillow's built-in AVIF support
            save_kwargs = {'format': 'AVIF', 'quality': quality}
            save_kwargs.update(
                _build_metadata_kwargs(
                    output_format_lower,
                    metadata,
                    preserve_icc=preserve_icc,
                    preserve_exif=preserve_exif,
                    preserve_xmp=preserve_xmp,
                )
            )
            if 'avif_speed' in advanced_options:
                save_kwargs['speed'] = int(advanced_options['avif_speed'])
            if 'avif_subsampling' in advanced_options:
                save_kwargs['subsampling'] = _subsampling_to_pillow_value(advanced_options['avif_subsampling'])
            if lossless:
                save_kwargs['quality'] = 100
                save_kwargs['lossless'] = True
            _save_with_fallback(img, output_img, save_kwargs)
            output_img.seek(0)
            return output_img
        except Exception as e:
            raise RuntimeError(f"AVIF encoding failed. Make sure pillow-avif-plugin is installed: {e}")
    
    # Handle WebP output using libwebp API
    if output_format_lower == 'webp':
        use_libwebp_fast_path = (
            libwebp
            and not preserve_icc
            and not preserve_exif
            and not preserve_xmp
            and not any(k.startswith('webp_') for k in advanced_options.keys())
        )
        if use_libwebp_fast_path:
            try:
                rgba_img = img.convert('RGBA')
                width, height = rgba_img.size
                rgba_data = rgba_img.tobytes()
                webp_data = encode_to_webp(rgba_data, width, height, quality, lossless)
                output_img = io.BytesIO(webp_data)
                output_img.seek(0)
                return output_img
            except Exception as e:
                # Fallback to PIL if libwebp fails
                print(f"libwebp encoding failed, using PIL fallback: {e}")
                output_img = io.BytesIO()
                img.save(output_img, format='WEBP', quality=quality, lossless=lossless)
                output_img.seek(0)
                return output_img
        else:
            # Use Pillow for richer control and metadata support.
            output_img = io.BytesIO()
            save_kwargs = {'format': 'WEBP', 'quality': quality, 'lossless': lossless}
            save_kwargs.update(
                _build_metadata_kwargs(
                    output_format_lower,
                    metadata,
                    preserve_icc=preserve_icc,
                    preserve_exif=preserve_exif,
                    preserve_xmp=preserve_xmp,
                )
            )
            if 'webp_method' in advanced_options:
                save_kwargs['method'] = int(advanced_options['webp_method'])
            if 'webp_alpha_quality' in advanced_options:
                save_kwargs['alpha_quality'] = int(advanced_options['webp_alpha_quality'])
            if 'webp_exact' in advanced_options:
                save_kwargs['exact'] = bool(advanced_options['webp_exact'])
            _save_with_fallback(img, output_img, save_kwargs)
            output_img.seek(0)
            return output_img
    
    # Convert to target format using PIL
    output_img = io.BytesIO()
    
    # Handle format-specific options
    save_kwargs = {}
    if output_format_lower in ['jpeg', 'jpg', 'jfif']:
        # Convert to RGB for JPEG. If alpha exists, composite against configurable background color.
        if _has_alpha_channel(img):
            rgba_img = img.convert('RGBA')
            rgb_img = Image.new('RGB', rgba_img.size, tuple(jpeg_background))
            rgb_img.paste(rgba_img, mask=rgba_img.split()[3])
            img = rgb_img
        elif img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Try MozJPEG optimization if requested and available
        can_use_mozjpeg = not (
            (preserve_icc and metadata.get('icc_profile'))
            or (preserve_exif and metadata.get('exif'))
            or (preserve_xmp and metadata.get('xmp'))
        )
        if optimize and can_use_mozjpeg:
            rgb_data = img.tobytes()
            optimized = optimize_jpeg_mozjpeg(rgb_data, img.size[0], img.size[1], quality)
            if optimized:
                output_img.write(optimized)
                output_img.seek(0)
                return output_img
        
        # Fallback to standard Pillow JPEG
        save_kwargs['quality'] = quality
        save_kwargs['format'] = 'JPEG'
        save_kwargs['progressive'] = bool(advanced_options.get('jpeg_progressive', False))
        if 'jpeg_subsampling' in advanced_options:
            save_kwargs['subsampling'] = _subsampling_to_pillow_value(advanced_options['jpeg_subsampling'])
        if optimize:
            save_kwargs['optimize'] = True
        save_kwargs.update(
            _build_metadata_kwargs(
                output_format_lower,
                metadata,
                preserve_icc=preserve_icc,
                preserve_exif=preserve_exif,
                preserve_xmp=preserve_xmp,
            )
        )
    elif output_format_lower == 'png':
        save_kwargs['format'] = 'PNG'
        if optimize:
            save_kwargs['optimize'] = True
        save_kwargs.update(
            _build_metadata_kwargs(
                output_format_lower,
                metadata,
                preserve_icc=preserve_icc,
                preserve_exif=preserve_exif,
                preserve_xmp=preserve_xmp,
            )
        )
    elif output_format_lower == 'bmp':
        if _has_alpha_channel(img):
            img = img.convert('RGB')
        elif img.mode not in ('RGB', 'L'):
            img = img.convert('RGB')
        save_kwargs['format'] = 'BMP'
    
    _save_with_fallback(img, output_img, save_kwargs)
    output_img.seek(0)
    
    # Apply PNG optimization tools if requested
    if output_format_lower == 'png' and optimize:
        png_data = output_img.getvalue()
        png_strip_mode = advanced_options.get('png_strip_metadata', 'safe')
        optimized_data = optimize_png(png_data, strip_mode=png_strip_mode)
        output_img = io.BytesIO(optimized_data)
        output_img.seek(0)
    
    return output_img
