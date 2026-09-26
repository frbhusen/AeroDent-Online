package com.aerodent.app;

import android.annotation.SuppressLint;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.Intent;
import android.content.SharedPreferences;
import android.graphics.Bitmap;
import android.net.ConnectivityManager;
import android.net.Network;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Bundle;
import android.os.Environment;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;

import androidx.activity.ComponentActivity;
import androidx.activity.OnBackPressedCallback;
import androidx.annotation.NonNull;
import androidx.core.graphics.Insets;
import androidx.core.view.ViewCompat;
import androidx.core.view.WindowCompat;
import androidx.core.view.WindowInsetsCompat;
import androidx.core.view.WindowInsetsControllerCompat;
import androidx.webkit.WebSettingsCompat;
import androidx.webkit.WebViewAssetLoader;
import androidx.webkit.WebViewFeature;

import java.util.Locale;

/**
 * A thin shell around the AeroDent web app. Everything (pages, API, authentication, data) stays
 * on the server configured at build time (BuildConfig.SERVER_URL); this activity only hosts it in
 * a locked-down WebView and adds what a browser tab would normally provide: file picking and
 * camera capture, downloads, printing, the Back button, and a "no connection" screen.
 *
 * The session is the server's HttpOnly cookie, kept by the WebView's cookie store. The app never
 * reads, copies or stores credentials itself.
 */
public class MainActivity extends ComponentActivity {

    private static final String ASSET_HOST = "appassets.androidplatform.net";
    private static final String OFFLINE_PAGE = "https://" + ASSET_HOST + "/assets/offline/offline.html";
    private static final String PREFS = "aerodent-shell";
    private static final String PREF_LANGUAGE = "language";

    private WebView webView;
    private Uri serverOrigin;
    private WebViewAssetLoader assetLoader;
    private FileChooser fileChooser;
    private ConnectivityManager.NetworkCallback networkCallback;

    /** Page to return to once the connection is back, while the offline screen is showing. */
    private String resumeUrl;
    private boolean showingOffline;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        serverOrigin = Uri.parse(BuildConfig.SERVER_URL);
        fileChooser = new FileChooser(this);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(getColor(R.color.shell_background));
        webView = new WebView(this);
        root.addView(webView, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        applyEdgeToEdge(root);

        configureWebView();
        new NativeChannel(this, webView, originOf(serverOrigin));

        getOnBackPressedDispatcher().addCallback(this, new OnBackPressedCallback(true) {
            @Override
            public void handleOnBackPressed() {
                handleBack();
            }
        });
        registerNetworkCallback();

        if (savedInstanceState == null || webView.restoreState(savedInstanceState) == null) {
            webView.loadUrl(startUrl());
        }
    }

    // ------------------------------------------------------------------ setup

    /**
     * Draws behind the system bars and pads the content by their size (and the keyboard's), so
     * nothing is hidden under a notch, status bar, gesture bar or on-screen keyboard.
     */
    private void applyEdgeToEdge(FrameLayout root) {
        WindowCompat.setDecorFitsSystemWindows(getWindow(), false);
        ViewCompat.setOnApplyWindowInsetsListener(root, (view, insets) -> {
            Insets bars = insets.getInsets(WindowInsetsCompat.Type.systemBars()
                    | WindowInsetsCompat.Type.displayCutout()
                    | WindowInsetsCompat.Type.ime());
            view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
            return WindowInsetsCompat.CONSUMED;
        });
        WindowInsetsControllerCompat controller = WindowCompat.getInsetsController(getWindow(), root);
        controller.setAppearanceLightStatusBars(false);
        controller.setAppearanceLightNavigationBars(false);
    }

    @SuppressLint("SetJavaScriptEnabled")
    private void configureWebView() {
        WebSettings settings = webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        // No access to device files except through the explicit file picker.
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        settings.setSupportZoom(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);
        settings.setUserAgentString(settings.getUserAgentString()
                + " AeroDentAndroid/" + BuildConfig.VERSION_NAME);
        if (WebViewFeature.isFeatureSupported(WebViewFeature.SAFE_BROWSING_ENABLE)) {
            WebSettingsCompat.setSafeBrowsingEnabled(settings, true);
        }

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(webView, false);
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG);

        assetLoader = new WebViewAssetLoader.Builder()
                .setDomain(ASSET_HOST)
                .addPathHandler("/assets/", new WebViewAssetLoader.AssetsPathHandler(this))
                .build();

        webView.setWebViewClient(new ShellClient());
        webView.setWebChromeClient(new ShellChromeClient());
        webView.setDownloadListener(this::onDownload);
    }

    private void registerNetworkCallback() {
        ConnectivityManager connectivity = getSystemService(ConnectivityManager.class);
        if (connectivity == null) return;
        networkCallback = new ConnectivityManager.NetworkCallback() {
            @Override
            public void onAvailable(@NonNull Network network) {
                runOnUiThread(() -> {
                    if (showingOffline && resumeUrl != null) {
                        webView.loadUrl(resumeUrl);
                    }
                });
            }
        };
        connectivity.registerDefaultNetworkCallback(networkCallback);
    }

    // ------------------------------------------------------------------ navigation

    private String startUrl() {
        return originOf(serverOrigin) + "/?mode=online";
    }

    private static String originOf(Uri uri) {
        String origin = uri.getScheme() + "://" + uri.getHost();
        return uri.getPort() == -1 ? origin : origin + ":" + uri.getPort();
    }

    private static int effectivePort(Uri uri) {
        if (uri.getPort() != -1) return uri.getPort();
        return "https".equalsIgnoreCase(uri.getScheme()) ? 443 : 80;
    }

    /** True only for URLs on the configured AeroDent server (same scheme, host and port). */
    private boolean isServer(Uri uri) {
        return uri != null
                && serverOrigin.getScheme().equalsIgnoreCase(uri.getScheme())
                && serverOrigin.getHost() != null
                && serverOrigin.getHost().equalsIgnoreCase(uri.getHost())
                && effectivePort(serverOrigin) == effectivePort(uri);
    }

    private static boolean isOfflinePage(Uri uri) {
        return uri != null && "https".equals(uri.getScheme()) && ASSET_HOST.equals(uri.getHost());
    }

    private void openExternally(Uri uri) {
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, uri).addCategory(Intent.CATEGORY_BROWSABLE));
        } catch (ActivityNotFoundException ignored) {
            // Nothing on the device can open it; stay on the current page.
        }
    }

    private void showOffline(String failedUrl) {
        Uri failed = failedUrl == null ? null : Uri.parse(failedUrl);
        resumeUrl = isServer(failed) ? failedUrl : startUrl();
        showingOffline = true;
        String page = OFFLINE_PAGE
                + "?lang=" + Uri.encode(preferredLanguage())
                + "&to=" + Uri.encode(resumeUrl);
        webView.loadUrl(page);
    }

    private String preferredLanguage() {
        SharedPreferences prefs = getSharedPreferences(PREFS, MODE_PRIVATE);
        String stored = prefs.getString(PREF_LANGUAGE, null);
        if (stored != null) return stored;
        return Locale.getDefault().getLanguage().startsWith("ar") ? "ar" : "en";
    }

    /** Remembers the UI language the user picked in the web app, for the offline screen. */
    private void rememberLanguage() {
        webView.evaluateJavascript(
                "(function(){try{return localStorage.getItem('aerodent-language');}catch(e){return null;}})()",
                value -> {
                    if ("\"ar\"".equals(value) || "\"en\"".equals(value)) {
                        getSharedPreferences(PREFS, MODE_PRIVATE).edit()
                                .putString(PREF_LANGUAGE, value.substring(1, 3))
                                .apply();
                    }
                });
    }

    private void handleBack() {
        if (showingOffline) {
            finish();
            return;
        }
        // Let the web app close its open dialog/drawer or go back to the dashboard first.
        webView.evaluateJavascript(
                "(function(){try{return !!(window.AeroDentBack && window.AeroDentBack());}catch(e){return false;}})()",
                handled -> {
                    if ("true".equals(handled)) return;
                    if (webView.canGoBack()) {
                        webView.goBack();
                    } else {
                        moveTaskToBack(true);
                    }
                });
    }

    // ------------------------------------------------------------------ downloads

    /**
     * Downloads served by the AeroDent server (e.g. an X-ray original). They are fetched by the
     * system download manager with the current session cookie, exactly as a browser would, and
     * land in Downloads/AeroDent. Generated files (blob:) are saved through NativeChannel.
     */
    private void onDownload(String url, String userAgent, String contentDisposition,
                            String mimeType, long contentLength) {
        Uri uri = Uri.parse(url);
        if (!isServer(uri)) return;
        String name = FileNames.fromContentDisposition(contentDisposition, url, mimeType);
        DownloadManager.Request request = new DownloadManager.Request(uri)
                .setTitle(name)
                .setMimeType(mimeType)
                .setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED)
                .setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, "AeroDent/" + name);
        String cookie = CookieManager.getInstance().getCookie(url);
        if (cookie != null) request.addRequestHeader("Cookie", cookie);
        request.addRequestHeader("User-Agent", userAgent);
        DownloadManager downloads = getSystemService(DownloadManager.class);
        if (downloads != null) downloads.enqueue(request);
    }

    // ------------------------------------------------------------------ lifecycle

    @Override
    protected void onResume() {
        super.onResume();
        webView.onResume();
    }

    @Override
    protected void onPause() {
        webView.onPause();
        CookieManager.getInstance().flush();
        super.onPause();
    }

    @Override
    protected void onSaveInstanceState(@NonNull Bundle outState) {
        super.onSaveInstanceState(outState);
        webView.saveState(outState);
    }

    @Override
    protected void onDestroy() {
        if (networkCallback != null) {
            ConnectivityManager connectivity = getSystemService(ConnectivityManager.class);
            if (connectivity != null) connectivity.unregisterNetworkCallback(networkCallback);
        }
        webView.destroy();
        super.onDestroy();
    }

    // ------------------------------------------------------------------ clients

    private final class ShellClient extends WebViewClient {

        @Override
        public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
            return assetLoader.shouldInterceptRequest(request.getUrl());
        }

        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            if (isServer(uri) || isOfflinePage(uri)) return false;
            // Anything else (email links, other websites) opens outside the app.
            openExternally(uri);
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            if (isServer(Uri.parse(url))) showingOffline = false;
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            if (isServer(Uri.parse(url))) rememberLanguage();
            CookieManager.getInstance().flush();
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (request.isForMainFrame() && !isOfflinePage(request.getUrl())) {
                showOffline(request.getUrl().toString());
            }
        }

        @SuppressLint("WebViewClientOnReceivedSslError")
        @Override
        public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
            // Never proceed past a certificate error.
            handler.cancel();
            showOffline(error.getUrl());
        }

        @Override
        public boolean onRenderProcessGone(WebView view, android.webkit.RenderProcessGoneDetail detail) {
            // The page's renderer crashed or was killed; start over with a fresh WebView.
            ((ViewGroup) view.getParent()).removeView(view);
            view.destroy();
            recreate();
            return true;
        }
    }

    private final class ShellChromeClient extends WebChromeClient {
        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback,
                                         FileChooserParams params) {
            return fileChooser.open(callback, params);
        }
    }
}
