// Frida script: SSL bypass + request body decompress
Java.perform(function() {
    console.log("[*] Video API capture loaded");

    // ========== 1. CertificatePinner bypass ==========
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(hostname, certs) {
            console.log("[+] CertPin bypassed: " + hostname);
        };
        CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(hostname, certs) {
            console.log("[+] CertPin(array) bypassed: " + hostname);
        };
        console.log("[*] CertificatePinner hooked");
    } catch(e) { console.log("[-] CertPin: " + e); }

    // ========== 2. Decompress helper ==========
    function decompressGzip(compressedBytes) {
        try {
            var GZIPInputStream = Java.use("java.util.zip.GZIPInputStream");
            var ByteArrayInputStream = Java.use("java.io.ByteArrayInputStream");
            var ByteArrayOutputStream = Java.use("java.io.ByteArrayOutputStream");

            var bais = ByteArrayInputStream.$new(compressedBytes);
            var gzis = GZIPInputStream.$new(bais);
            var baos = ByteArrayOutputStream.$new();

            var buf = Java.array('byte', new Array(4096));
            var len;
            while ((len = gzis.read(buf)) > 0) {
                baos.write(buf, 0, len);
            }
            gzis.close();
            var result = baos.toString("UTF-8");
            baos.close();
            return result;
        } catch(e) {
            return null;
        }
    }

    function isGzip(bytes) {
        return bytes.length >= 2 && (bytes[0] & 0xFF) === 0x1f && (bytes[1] & 0xFF) === 0x8b;
    }

    function isVideoApi(url) {
        return (url.indexOf("multi_video_model") >= 0 ||
                url.indexOf("multi_video_detail") >= 0 ||
                url.indexOf("video_detail") >= 0 ||
                url.indexOf("video_model") >= 0 ||
                url.indexOf("vod/get") >= 0 ||
                url.indexOf("play_info") >= 0 ||
                url.indexOf("player/video") >= 0 ||
                url.indexOf("player/multi_video") >= 0 ||
                url.indexOf("fqnovel.com/novel/player") >= 0);
    }

    // ========== 3. OkHttpClient.newCall - capture ALL requests with decompression ==========
    try {
        var OkHttpClient = Java.use("okhttp3.OkHttpClient");
        OkHttpClient.newCall.implementation = function(request) {
            var url = request.url().toString();
            var method = request.method();

            // Log all requests
            console.log("[HTTP] " + method + " " + url);

            if (isVideoApi(url)) {
                console.log("\n========== VIDEO API REQUEST ==========");
                console.log("[REQ] " + method + " " + url);

                var headers = request.headers();
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  " + headers.name(i) + ": " + headers.value(i));
                }

                var body = request.body();
                if (body != null) {
                    try {
                        var Buffer = Java.use("okio.Buffer");
                        var buffer = Buffer.$new();
                        body.writeTo(buffer);
                        var rawBytes = buffer.readByteArray();

                        if (isGzip(rawBytes)) {
                            console.log("  BODY-RAW: gzip compressed, " + rawBytes.length + " bytes");
                            var decompressed = decompressGzip(rawBytes);
                            if (decompressed) {
                                console.log("  BODY-JSON:");
                                console.log("  " + decompressed);
                            } else {
                                console.log("  BODY: [decompress failed]");
                            }
                        } else {
                            var bodyStr = buffer.readUtf8();
                            if (bodyStr.length > 10000) {
                                bodyStr = bodyStr.substring(0, 5000) + "...(truncated, total=" + bodyStr.length + ")";
                            }
                            console.log("  BODY: " + bodyStr);
                        }
                    } catch(e) {
                        console.log("  BODY: [read error: " + e + "]");
                    }
                }
                console.log("========== END REQUEST ==========\n");
            }

            return this.newCall(request);
        };
        console.log("[*] OkHttpClient.newCall hooked");
    } catch(e) { console.log("[-] OkHttpClient: " + e); }

    console.log("[*] Init complete - waiting for video API calls...");
});
