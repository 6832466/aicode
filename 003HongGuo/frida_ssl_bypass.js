// Frida SSL pinning bypass for HongGuo - Universal network capture
Java.perform(function() {
    console.log("[*] Universal Network Capture loaded");

    // 1. OkHttp CertificatePinner bypass
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

    // 2. OkHttp Client hook
    try {
        var OkHttpClient = Java.use("okhttp3.OkHttpClient");
        OkHttpClient.newCall.implementation = function(request) {
            var url = request.url().toString();
            console.log("[OKHTTP] " + request.method() + " " + url);
            var headers = request.headers();
            for (var i = 0; i < headers.size(); i++) {
                console.log("  " + headers.name(i) + ": " + headers.value(i));
            }
            return this.newCall(request);
        };
        console.log("[*] OkHttpClient hooked");
    } catch(e) { console.log("[-] OkHttpClient: " + e); }

    // 3. Cronet URL Request hook
    try {
        var CronetUrlRequest = Java.use("org.chromium.net.impl.CronetUrlRequest");
        CronetUrlRequest.start.implementation = function() {
            try {
                console.log("[CRONET] Starting request: " + this.getCurrentUrl());
            } catch(e) {}
            return this.start();
        };
        console.log("[*] CronetUrlRequest hooked");
    } catch(e) { console.log("[-] Cronet: " + e); }

    // 4. HttpsURLConnection hook
    try {
        var HttpsURLConnection = Java.use("javax.net.ssl.HttpsURLConnection");
        HttpsURLConnection.connect.implementation = function() {
            try {
                console.log("[HTTPS] Connecting to: " + this.getURL().toString());
            } catch(e) {}
            return this.connect();
        };
        console.log("[*] HttpsURLConnection hooked");
    } catch(e) { console.log("[-] HttpsURLConnection: " + e); }

    // 5. Socket connection hook (catches everything)
    try {
        var Socket = Java.use("java.net.Socket");
        Socket.connect.overload('java.net.SocketAddress').implementation = function(endpoint) {
            var addr = endpoint.toString();
            if (addr.indexOf("snssdk") >= 0 || addr.indexOf("fqnovel") >= 0 ||
                addr.indexOf("vod") >= 0 || addr.indexOf("play") >= 0) {
                console.log("[SOCKET] Connecting to: " + addr);
            }
            return this.connect(endpoint);
        };
        Socket.connect.overload('java.net.SocketAddress', 'int').implementation = function(endpoint, timeout) {
            var addr = endpoint.toString();
            if (addr.indexOf("snssdk") >= 0 || addr.indexOf("fqnovel") >= 0 ||
                addr.indexOf("vod") >= 0 || addr.indexOf("play") >= 0) {
                console.log("[SOCKET] Connecting to: " + addr + " (timeout=" + timeout + ")");
            }
            return this.connect(endpoint, timeout);
        };
        console.log("[*] Socket hooked");
    } catch(e) { console.log("[-] Socket: " + e); }

    // 6. TrustManager bypass
    try {
        var TrustManagerImpl = Java.use('com.android.org.conscrypt.TrustManagerImpl');
        if (TrustManagerImpl.verifyChain) {
            TrustManagerImpl.verifyChain.implementation = function(chain, authType, host, engine, socket) {
                console.log("[+] TrustManager: " + host);
            };
        }
        console.log("[*] TrustManagerImpl hooked");
    } catch(e) { console.log("[-] TrustManager: " + e); }

    // 7. Hook CronetEngine to capture URL requests
    try {
        var CronetEngine = Java.use("org.chromium.net.impl.CronetUrlRequestContext");
        // Just log that Cronet is available
        console.log("[*] CronetEngine available");
    } catch(e) {}

    // 8. Hook URL.openConnection for standard Java HTTP
    try {
        var URL = Java.use("java.net.URL");
        URL.openConnection.implementation = function() {
            var url = this.toString();
            if (url.indexOf("snssdk") >= 0 || url.indexOf("fqnovel") >= 0 ||
                url.indexOf("vod") >= 0 || url.indexOf("play") >= 0) {
                console.log("[URL] openConnection: " + url);
            }
            return this.openConnection();
        };
        console.log("[*] URL.openConnection hooked");
    } catch(e) { console.log("[-] URL: " + e); }

    console.log("[*] Universal capture init complete");
});
