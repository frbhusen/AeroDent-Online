package com.aerodent.app;

import android.content.ContentResolver;
import android.content.ContentValues;
import android.net.Uri;
import android.os.Bundle;
import android.os.CancellationSignal;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.ParcelFileDescriptor;
import android.print.PageRange;
import android.print.PrintAttributes;
import android.print.PrintDocumentAdapter;
import android.print.PrintManager;
import android.provider.MediaStore;
import android.util.Base64;
import android.webkit.WebView;

import androidx.activity.ComponentActivity;
import androidx.annotation.NonNull;
import androidx.webkit.JavaScriptReplyProxy;
import androidx.webkit.WebMessageCompat;
import androidx.webkit.WebViewCompat;
import androidx.webkit.WebViewFeature;

import org.json.JSONException;
import org.json.JSONObject;

import java.io.OutputStream;
import java.util.Collections;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * Message channel used by web/js/nativeBridge.js. It is injected as `window.AeroDentNative` only
 * into top-level pages from the configured server origin, so no other page (including the
 * offline screen or any external site) can use it. It carries no credentials and offers only:
 *
 *   {type: "download", id, name, mime, data(base64)}  -> saves a generated file to Downloads/AeroDent
 *   {type: "print", id, name}                          -> prints the current page
 *
 * Each request is answered with {id, ok[, error]}.
 */
final class NativeChannel implements WebViewCompat.WebMessageListener {

    static final String NAME = "AeroDentNative";
    /** Upper bound for one generated file (base64 characters), well above any clinic export. */
    private static final int MAX_BASE64_CHARS = 200 * 1024 * 1024;

    private final ComponentActivity activity;
    private final WebView webView;
    private final Handler main = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();

    NativeChannel(ComponentActivity activity, WebView webView, String allowedOrigin) {
        this.activity = activity;
        this.webView = webView;
        if (WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) {
            WebViewCompat.addWebMessageListener(webView, NAME, Collections.singleton(allowedOrigin), this);
        }
    }

    @Override
    public void onPostMessage(@NonNull WebView view, @NonNull WebMessageCompat message,
                              @NonNull Uri sourceOrigin, boolean isMainFrame,
                              @NonNull JavaScriptReplyProxy reply) {
        if (!isMainFrame || message.getData() == null) return;
        JSONObject request;
        try {
            request = new JSONObject(message.getData());
        } catch (JSONException e) {
            return;
        }
        int id = request.optInt("id", -1);
        switch (request.optString("type")) {
            case "download":
                io.execute(() -> {
                    String error = saveDownload(request);
                    main.post(() -> respond(reply, id, error));
                });
                break;
            case "print":
                print(request.optString("name", "AeroDent"), () -> respond(reply, id, null));
                break;
            default:
                respond(reply, id, "unsupported");
        }
    }

    private static void respond(JavaScriptReplyProxy reply, int id, String error) {
        // Only reachable through onPostMessage, which exists only when this feature is supported.
        if (!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)) return;
        JSONObject response = new JSONObject();
        try {
            response.put("id", id);
            response.put("ok", error == null);
            if (error != null) response.put("error", error);
        } catch (JSONException ignored) {
            return;
        }
        reply.postMessage(response.toString());
    }

    /** Returns null on success, or a short error code. */
    private String saveDownload(JSONObject request) {
        String data = request.optString("data", "");
        if (data.isEmpty() || data.length() > MAX_BASE64_CHARS) return "invalid-size";
        byte[] bytes;
        try {
            bytes = Base64.decode(data, Base64.DEFAULT);
        } catch (IllegalArgumentException e) {
            return "invalid-data";
        }
        String name = FileNames.sanitize(request.optString("name", "aerodent-file"));
        String mime = request.optString("mime", "application/octet-stream");
        if (!mime.matches("[\\w.+-]+/[\\w.+-]+")) mime = "application/octet-stream";

        ContentResolver resolver = activity.getContentResolver();
        ContentValues values = new ContentValues();
        values.put(MediaStore.Downloads.DISPLAY_NAME, name);
        values.put(MediaStore.Downloads.MIME_TYPE, mime);
        values.put(MediaStore.Downloads.RELATIVE_PATH, Environment.DIRECTORY_DOWNLOADS + "/AeroDent");
        values.put(MediaStore.Downloads.IS_PENDING, 1);
        Uri target = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values);
        if (target == null) return "storage-unavailable";
        try (OutputStream out = resolver.openOutputStream(target)) {
            if (out == null) throw new java.io.IOException("no stream");
            out.write(bytes);
        } catch (Exception e) {
            resolver.delete(target, null, null);
            return "write-failed";
        }
        values.clear();
        values.put(MediaStore.Downloads.IS_PENDING, 0);
        resolver.update(target, values, null, null);
        return null;
    }

    /** Prints the page as rendered with its print stylesheet; `done` runs when the job UI closes. */
    private void print(String jobName, Runnable done) {
        PrintManager printManager = activity.getSystemService(PrintManager.class);
        if (printManager == null) {
            done.run();
            return;
        }
        String name = FileNames.sanitize(jobName);
        PrintDocumentAdapter inner = webView.createPrintDocumentAdapter(name);
        printManager.print(name, new PrintDocumentAdapter() {
            @Override
            public void onStart() {
                inner.onStart();
            }

            @Override
            public void onLayout(PrintAttributes oldAttributes, PrintAttributes newAttributes,
                                 CancellationSignal cancellationSignal, LayoutResultCallback callback,
                                 Bundle extras) {
                inner.onLayout(oldAttributes, newAttributes, cancellationSignal, callback, extras);
            }

            @Override
            public void onWrite(PageRange[] pages, ParcelFileDescriptor destination,
                                CancellationSignal cancellationSignal, WriteResultCallback callback) {
                inner.onWrite(pages, destination, cancellationSignal, callback);
            }

            @Override
            public void onFinish() {
                inner.onFinish();
                done.run();
            }
        }, new PrintAttributes.Builder().build());
    }
}
