package com.aerodent.app;

import android.app.Activity;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.net.Uri;
import android.provider.MediaStore;
import android.webkit.MimeTypeMap;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient.FileChooserParams;

import androidx.activity.ComponentActivity;
import androidx.activity.result.ActivityResult;
import androidx.activity.result.ActivityResultLauncher;
import androidx.activity.result.contract.ActivityResultContracts;
import androidx.core.content.FileProvider;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;

/**
 * Backs <input type="file"> in the WebView: offers the system file/gallery picker and, when the
 * input accepts images, "take a photo" through the camera app. Files are handed to the page
 * untouched; the server does all validation and stores X-rays losslessly.
 */
final class FileChooser {

    private static final long STALE_CAPTURE_MS = 24L * 60 * 60 * 1000;

    private final ComponentActivity activity;
    private final ActivityResultLauncher<Intent> launcher;
    private ValueCallback<Uri[]> callback;
    private File captureFile;
    private Uri captureUri;

    FileChooser(ComponentActivity activity) {
        this.activity = activity;
        this.launcher = activity.registerForActivityResult(
                new ActivityResultContracts.StartActivityForResult(), this::onResult);
        deleteStaleCaptures();
    }

    boolean open(ValueCallback<Uri[]> newCallback, FileChooserParams params) {
        finish(null);
        callback = newCallback;

        String[] mimeTypes = acceptedMimeTypes(params.getAcceptTypes());
        Intent content = new Intent(Intent.ACTION_GET_CONTENT)
                .addCategory(Intent.CATEGORY_OPENABLE)
                .setType(mimeTypes.length == 1 ? mimeTypes[0] : "*/*")
                .putExtra(Intent.EXTRA_ALLOW_MULTIPLE, params.getMode() == FileChooserParams.MODE_OPEN_MULTIPLE);
        if (mimeTypes.length > 1) content.putExtra(Intent.EXTRA_MIME_TYPES, mimeTypes);

        Intent chooser = Intent.createChooser(content, null);
        Intent camera = acceptsImages(mimeTypes) ? cameraIntent() : null;
        if (camera != null) chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, new Intent[]{camera});

        try {
            launcher.launch(chooser);
            return true;
        } catch (ActivityNotFoundException e) {
            finish(null);
            return false;
        }
    }

    private void onResult(ActivityResult result) {
        Uri[] uris = null;
        if (result.getResultCode() == Activity.RESULT_OK) {
            uris = pickedUris(result.getData());
            if (uris == null && captureFile != null && captureFile.length() > 0) {
                uris = new Uri[]{captureUri};
            }
        }
        finish(uris);
    }

    private void finish(Uri[] uris) {
        if (callback != null) {
            callback.onReceiveValue(uris);
            callback = null;
        }
        if (uris == null && captureFile != null) {
            //noinspection ResultOfMethodCallIgnored
            captureFile.delete();
        }
        captureFile = null;
        captureUri = null;
    }

    private static Uri[] pickedUris(Intent data) {
        if (data == null) return null;
        ClipData clip = data.getClipData();
        if (clip != null && clip.getItemCount() > 0) {
            Uri[] uris = new Uri[clip.getItemCount()];
            for (int i = 0; i < uris.length; i++) uris[i] = clip.getItemAt(i).getUri();
            return uris;
        }
        return data.getData() != null ? new Uri[]{data.getData()} : null;
    }

    /**
     * Converts the input's accept list (".png", "image/*", ...) to MIME types. Returns an empty
     * array (meaning "any file") if the list is empty or contains something with no known MIME
     * type, so the picker never hides a file the page would accept.
     */
    private static String[] acceptedMimeTypes(String[] acceptTypes) {
        Set<String> result = new LinkedHashSet<>();
        if (acceptTypes == null) return new String[0];
        for (String raw : acceptTypes) {
            for (String part : raw.split(",")) {
                String type = part.trim().toLowerCase(Locale.ROOT);
                if (type.isEmpty()) continue;
                if (type.startsWith(".")) {
                    type = MimeTypeMap.getSingleton().getMimeTypeFromExtension(type.substring(1));
                    if (type == null) return new String[0];
                }
                if (type.equals("*/*")) return new String[0];
                result.add(type);
            }
        }
        return result.toArray(new String[0]);
    }

    private static boolean acceptsImages(String[] mimeTypes) {
        if (mimeTypes.length == 0) return true;
        for (String type : mimeTypes) {
            if (type.startsWith("image/")) return true;
        }
        return false;
    }

    private Intent cameraIntent() {
        Intent intent = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
        if (intent.resolveActivity(activity.getPackageManager()) == null) return null;
        try {
            File dir = new File(activity.getCacheDir(), "camera");
            if (!dir.isDirectory() && !dir.mkdirs()) return null;
            captureFile = File.createTempFile("capture-", ".jpg", dir);
        } catch (IOException e) {
            return null;
        }
        captureUri = FileProvider.getUriForFile(activity, activity.getPackageName() + ".fileprovider", captureFile);
        return intent.putExtra(MediaStore.EXTRA_OUTPUT, captureUri)
                .addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION | Intent.FLAG_GRANT_READ_URI_PERMISSION);
    }

    /**
     * Captured photos stay in the private cache until the page has uploaded them; anything older
     * than a day is removed on the next start.
     */
    private void deleteStaleCaptures() {
        File[] files = new File(activity.getCacheDir(), "camera").listFiles();
        if (files == null) return;
        long cutoff = System.currentTimeMillis() - STALE_CAPTURE_MS;
        List<File> stale = new ArrayList<>();
        for (File file : files) if (file.lastModified() < cutoff) stale.add(file);
        //noinspection ResultOfMethodCallIgnored
        for (File file : stale) file.delete();
    }
}
