package com.aerodent.app;

import android.webkit.URLUtil;

import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Safe file names for files saved to the device. */
final class FileNames {

    private static final Pattern FILENAME_STAR =
            Pattern.compile("filename\\*\\s*=\\s*UTF-8''([^;]+)", Pattern.CASE_INSENSITIVE);
    private static final Pattern FILENAME =
            Pattern.compile("filename\\s*=\\s*\"?([^\";]+)\"?", Pattern.CASE_INSENSITIVE);
    private static final int MAX_LENGTH = 120;

    private FileNames() {
    }

    /** Uses the server's Content-Disposition name (including RFC 5987 UTF-8 names). */
    static String fromContentDisposition(String contentDisposition, String url, String mimeType) {
        String name = null;
        if (contentDisposition != null) {
            Matcher star = FILENAME_STAR.matcher(contentDisposition);
            if (star.find()) {
                try {
                    name = URLDecoder.decode(star.group(1).trim(), StandardCharsets.UTF_8.name());
                } catch (Exception ignored) {
                    name = null;
                }
            }
            if (name == null) {
                Matcher plain = FILENAME.matcher(contentDisposition);
                if (plain.find()) name = plain.group(1).trim();
            }
        }
        if (name == null || name.isEmpty()) name = URLUtil.guessFileName(url, contentDisposition, mimeType);
        return sanitize(name);
    }

    /** Strips path separators and control characters so a name can never escape its folder. */
    static String sanitize(String name) {
        String cleaned = name == null ? "" : name.replaceAll("[\\\\/:*?\"<>|\\p{Cntrl}]", "_").trim();
        while (cleaned.startsWith(".")) cleaned = cleaned.substring(1);
        if (cleaned.isEmpty()) cleaned = "aerodent-file";
        if (cleaned.length() > MAX_LENGTH) {
            int dot = cleaned.lastIndexOf('.');
            String ext = dot > 0 && cleaned.length() - dot <= 10 ? cleaned.substring(dot) : "";
            cleaned = cleaned.substring(0, MAX_LENGTH - ext.length()) + ext;
        }
        return cleaned;
    }
}
