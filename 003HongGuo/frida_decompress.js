// Frida SSL bypass + gzip decompression for video API capture
Java.perform(function() {
    console.log("[*] Decompress capture loaded");

    // 1. CertificatePinner bypass
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

    // Helper to decompress gzip
    function decompressGzip(compressed) {
        try {
            var GZIPInputStream = Java.use("java.util.zip.GZIPInputStream");
            var ByteArrayInputStream = Java.use("java.io.ByteArrayInputStream");
            var ByteArrayOutputStream = Java.use("java.io.ByteArrayOutputStream");

            var bais = ByteArrayInputStream.$new(compressed);
            var gzis = GZIPInputStream.$new(bais);
            var baos = ByteArrayOutputStream.$new();

            var buffer = Java.array('byte', new Array(1024));
            var len;
            while ((len = gzis.read(buffer)) > 0) {
                baos.write(buffer, 0, len);
            }
            gzis.close();
            var result = baos.toString("UTF-8");
            baos.close();
            return result;
        } catch(e) {
            return "[decompress error: " + e + "]";
        }
    }

    // 2. OkHttpClient.newCall - capture with gzip decompression
    try {
        var OkHttpClient = Java.use("okhttp3.OkHttpClient");
        OkHttpClient.newCall.implementation = function(request) {
            var url = request.url().toString();
            var method = request.method();

            // Only log video-related requests in detail
            var isVideoApi = (url.indexOf("video_detail") >= 0 || url.indexOf("video_model") >= 0 ||
                              url.indexOf("vod/get") >= 0 || url.indexOf("play_info") >= 0 ||
                              url.indexOf("player/video") >= 0 || url.indexOf("player/multi_video") >= 0);

            // For all other requests, just log URL
            if (!isVideoApi) {
                console.log("[OKHTTP] " + method + " " + url);
                return this.newCall(request);
            }

            console.log("\n*** VIDEO API REQUEST ***");
            console.log("[REQ] " + method + " " + url);

            var headers = request.headers();
            for (var i = 0; i < headers.size(); i++) {
                console.log("  " + headers.name(i) + ": " + headers.value(i));
            }

            if (method === "POST") {
                var body = request.body();
                if (body != null) {
                    try {
                        var Buffer = Java.use("okio.Buffer");
                        var buffer = Buffer.$new();
                        body.writeTo(buffer);
                        var rawBytes = buffer.readByteArray();

                        // Check if gzip compressed
                        var contentEncoding = request.header("Content-Encoding");
                        if (contentEncoding && contentEncoding.indexOf("gzip") >= 0) {
                            var decompressed = decompressGzip(rawBytes);
                            console.log("  BODY (decompressed): " + decompressed);
                        } else {
                            console.log("  BODY (raw): " + buffer.readUtf8());
                        }
                    } catch(e) {
                        console.log("  BODY: [error: " + e + "]");
                    }
                }
            }
            console.log("*** END REQUEST ***\n");

            return this.newCall(request);
        };
        console.log("[*] OkHttpClient hooked");
    } catch(e) { console.log("[-] OkHttpClient: " + e); }

    // 3. Hook RealCall.getResponseWithInterceptorChain for responses
    try {
        var RealCall = Java.use("okhttp3.RealCall");
        var getResponseMethod = RealCall.getResponseWithInterceptorChain;
        getResponseMethod.implementation = function() {
            var response = getResponseMethod.call(this);
            var request = this.request();
            var url = request.url().toString();

            var isVideoApi = (url.indexOf("video_detail") >= 0 || url.indexOf("video_model") >= 0 ||
                              url.indexOf("vod/get") >= 0 || url.indexOf("play_info") >= 0 ||
                              url.indexOf("player/video") >= 0 || url.indexOf("player/multi_video") >= 0);

            if (isVideoApi) {
                console.log("\n*** VIDEO API RESPONSE ***");
                console.log("[RESP] " + url);
                console.log("  Status: " + response.code());

                try {
                    var body = response.body();
                    if (body != null) {
                        var source = body.source();
                        if (source != null) {
                            var Buffer = Java.use("okio.Buffer");
                            var buffer = Buffer.$new();
                            buffer.writeAll(source);
                            var rawBytes = buffer.readByteArray();

                            // Try decompress if gzip
                            var contentEncoding = response.header("Content-Encoding");
                            if (contentEncoding && contentEncoding.indexOf("gzip") >= 0) {
                                var decompressed = decompressGzip(rawBytes);
                                console.log("  RESPONSE BODY: " + decompressed);
                            } else {
                                console.log("  RESPONSE BODY (raw): " + buffer.readUtf8());
                            }
                        }
                    }
                } catch(e) {
                    console.log("  RESPONSE BODY: [error: " + e + "]");
                }
                console.log("*** END RESPONSE ***\n");
            }

            return response;
        };
        console.log("[*] RealCall.getResponseWithInterceptorChain hooked");
    } catch(e) { console.log("[-] Response hook: " + e); }

    console.log("[*] Decompress capture init complete");
});
