// Frida script to capture OkHttp request/response bodies for video API
Java.perform(function() {
    console.log("[*] Body Capture loaded");

    // Hook Request.Builder to capture request body
    try {
        var RequestBuilder = Java.use("okhttp3.Request$Builder");

        // Hook the build method to capture the final request
        var originalBuild = RequestBuilder.build;
        RequestBuilder.build.implementation = function() {
            var request = originalBuild.call(this);
            var url = request.url().toString();
            var method = request.method();

            // Only log video-related requests
            if (url.indexOf("video_detail") >= 0 || url.indexOf("video_model") >= 0 ||
                url.indexOf("vod") >= 0 || url.indexOf("player") >= 0 ||
                url.indexOf("snssdk.com/vod") >= 0) {

                console.log("\n=== CAPTURED ===");
                console.log("[REQ] " + method + " " + url);

                // Log headers
                var headers = request.headers();
                for (var i = 0; i < headers.size(); i++) {
                    console.log("  Header: " + headers.name(i) + ": " + headers.value(i));
                }

                // Log body
                var body = request.body();
                if (body != null) {
                    try {
                        var Buffer = Java.use("okio.Buffer");
                        var buffer = Buffer.$new();
                        body.writeTo(buffer);
                        var bodyStr = buffer.readUtf8();
                        console.log("  Body: " + bodyStr);
                    } catch(e) {
                        console.log("  Body: [error reading: " + e + "]");
                        console.log("  Body type: " + body.getClass().getName());
                    }
                } else {
                    console.log("  Body: [null]");
                }
                console.log("=== END CAPTURED ===\n");
            }

            return request;
        };
        console.log("[*] Request.Builder.build hooked");
    } catch(e) { console.log("[-] Request.Builder: " + e); }

    // Also hook RealCall to capture response bodies
    try {
        var RealCall = Java.use("okhttp3.RealCall");
        RealCall.execute.implementation = function() {
            var request = this.request();
            var url = request.url().toString();

            var response = this.execute();

            if (url.indexOf("video_detail") >= 0 || url.indexOf("video_model") >= 0 ||
                url.indexOf("vod") >= 0 || url.indexOf("player") >= 0 ||
                url.indexOf("snssdk.com/vod") >= 0) {

                console.log("\n=== RESPONSE ===");
                console.log("[RESP] " + url);
                console.log("  Status: " + response.code());

                var body = response.body();
                if (body != null) {
                    try {
                        var source = body.source();
                        var Buffer = Java.use("okio.Buffer");
                        var buffer = Buffer.$new();
                        buffer.writeAll(source);
                        var bodyStr = buffer.readUtf8();
                        if (bodyStr.length > 2000) {
                            console.log("  Body (truncated): " + bodyStr.substring(0, 2000) + "...");
                        } else {
                            console.log("  Body: " + bodyStr);
                        }
                    } catch(e) {
                        console.log("  Body: [error: " + e + "]");
                    }
                }
                console.log("=== END RESPONSE ===\n");
            }

            return response;
        };
        console.log("[*] RealCall.execute hooked");
    } catch(e) { console.log("[-] RealCall: " + e); }

    // Hook CertificatePinner
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload('java.lang.String', 'java.util.List').implementation = function(hostname, certs) {
            console.log("[+] CertPin bypassed: " + hostname);
        };
        CertificatePinner.check.overload('java.lang.String', '[Ljava.security.cert.Certificate;').implementation = function(hostname, certs) {
            console.log("[+] CertPin(array) bypassed: " + hostname);
        };
        console.log("[*] CertificatePinner hooked");
    } catch(e) {}

    console.log("[*] Body capture init complete");
});
