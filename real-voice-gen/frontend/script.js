document.addEventListener('DOMContentLoaded', () => {
    const generateBtn = document.getElementById('generate-btn');
    const textInput = document.getElementById('text-input');
    const resultContainer = document.getElementById('result-container');
    const audioPlayer = document.getElementById('audio-player');
    const downloadLink = document.getElementById('download-link');
    const errorMessage = document.getElementById('error-message');
    const btnText = document.querySelector('.btn-text');
    const loader = document.querySelector('.loader');

    generateBtn.addEventListener('click', async () => {
        const text = textInput.value.trim();

        const removeSilence = document.getElementById('remove-silence').checked;

        if (!text) {
            showError("Please enter some text.");
            return;
        }

        // Reset UI
        hideError();
        resultContainer.classList.add('hidden');
        generateBtn.disabled = true;
        btnText.classList.add('hidden');
        loader.classList.remove('hidden');

        try {
            const response = await fetch('/api/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ text: text, remove_silence: removeSilence })
            });

            if (!response.ok) {
                let errData;
                try {
                    errData = await response.json();
                } catch(e) {
                    throw new Error("Failed to generate audio");
                }
                throw new Error(errData.detail || "Failed to generate audio");
            }

            const blob = await response.blob();
            const audio_url = URL.createObjectURL(blob);
            
            // Set audio source
            audioPlayer.src = audio_url;
            downloadLink.href = audio_url;
            
            // Show result
            resultContainer.classList.remove('hidden');
            audioPlayer.play().catch(e => console.log("Auto-play prevented", e));
            
        } catch (error) {
            showError(error.message);
        } finally {
            generateBtn.disabled = false;
            btnText.classList.remove('hidden');
            loader.classList.add('hidden');
        }
    });

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.classList.remove('hidden');
    }

    function hideError() {
        errorMessage.classList.add('hidden');
    }
});
