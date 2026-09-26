package com.aerodent.app;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

import org.junit.Test;

public class FileNamesTest {

    @Test
    public void usesRfc5987Utf8Name() {
        String name = FileNames.fromContentDisposition(
                "attachment; filename=\"xray.png\"; filename*=UTF-8''%D8%A3%D8%B4%D8%B9%D8%A9.png",
                "https://clinic.example.com/api/x-rays/1/file?download=1", "image/png");
        assertEquals("أشعة.png", name);
    }

    @Test
    public void usesPlainFilename() {
        assertEquals("panoramic.tiff", FileNames.fromContentDisposition(
                "attachment; filename=\"panoramic.tiff\"", "https://x/y", "image/tiff"));
    }

    @Test
    public void pathTraversalCannotEscapeTheFolder() {
        String name = FileNames.fromContentDisposition(
                "attachment; filename=\"../../data/evil.sh\"", "https://x/y", "text/plain");
        assertFalse(name.contains("/"));
        assertFalse(name.startsWith("."));
        assertEquals("_.._data_evil.sh", name);
    }

    @Test
    public void stripsControlAndReservedCharacters() {
        String name = FileNames.sanitize("a\u0000b\nc:d*e?f\"g<h>i|j\\k.txt");
        assertTrue(name.matches("[A-Za-z_.]+"));
        assertTrue(name.endsWith(".txt"));
    }

    @Test
    public void emptyAndHiddenNamesGetADefault() {
        assertEquals("aerodent-file", FileNames.sanitize(""));
        assertEquals("aerodent-file", FileNames.sanitize("..."));
        assertEquals("env", FileNames.sanitize(".env"));
    }

    @Test
    public void longNamesKeepTheirExtension() {
        String name = FileNames.sanitize("x".repeat(300) + ".json");
        assertEquals(120, name.length());
        assertTrue(name.endsWith(".json"));
    }
}
