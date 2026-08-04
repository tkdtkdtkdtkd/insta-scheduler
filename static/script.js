document.addEventListener('DOMContentLoaded', () => {
    const generateBtn = document.getElementById('generate-btn');
    const scheduleBtn = document.getElementById('schedule-btn');
    const textInput = document.getElementById('text-input');
    const captionInput = document.getElementById('caption-input');
    const scheduledTimeInput = document.getElementById('scheduled-time');
    const removeSilenceCheckbox = document.getElementById('remove-silence');
    
    const statusPanel = document.getElementById('status-panel');
    const progressBar = document.getElementById('progress-bar');
    const progressText = document.getElementById('progress-text');
    
    const resultContainer = document.getElementById('result-container');
    const videoPlayer = document.getElementById('video-player');
    const errorMessage = document.getElementById('error-message');
    const scheduleSuccess = document.getElementById('schedule-success');
    
    let generatedFilename = null;
    let pollInterval = null;

    function showError(msg) {
        errorMessage.textContent = msg;
        errorMessage.classList.remove('hidden');
    }

    function hideError() {
        errorMessage.classList.add('hidden');
        errorMessage.textContent = '';
    }

    function updateProgress() {
        fetch('/progress')
            .then(res => res.json())
            .then(data => {
                progressBar.style.width = `${data.percent}%`;
                progressText.textContent = data.status;
            })
            .catch(err => console.error("Error fetching progress:", err));
    }

    generateBtn.addEventListener('click', async () => {
        const text = textInput.value.trim();
        if (!text) {
            showError("Please enter some text!");
            return;
        }

        hideError();
        scheduleSuccess.classList.add('hidden');
        resultContainer.classList.add('hidden');
        statusPanel.classList.remove('hidden');
        
        generateBtn.disabled = true;
        generateBtn.querySelector('.btn-text').textContent = "Generating...";
        generateBtn.querySelector('.loader').classList.remove('hidden');
        
        // Start polling progress
        pollInterval = setInterval(updateProgress, 500);

        try {
            const response = await fetch('/generate', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text: text,
                    aspect_ratio: '9:16',
                    remove_silence: removeSilenceCheckbox.checked
                })
            });

            const data = await response.json();
            
            clearInterval(pollInterval);
            
            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Generation failed');
            }

            // Success
            progressBar.style.width = "100%";
            progressText.textContent = "Complete!";
            
            videoPlayer.src = data.video_url;
            generatedFilename = data.filename;
            
            resultContainer.classList.remove('hidden');
            
        } catch (err) {
            clearInterval(pollInterval);
            showError(err.message);
            statusPanel.classList.add('hidden');
        } finally {
            generateBtn.disabled = false;
            generateBtn.querySelector('.btn-text').textContent = "Generate Video & Preview";
            generateBtn.querySelector('.loader').classList.add('hidden');
        }
    });

    scheduleBtn.addEventListener('click', async () => {
        const caption = captionInput.value;
        const scheduledTime = scheduledTimeInput.value;
        
        if (!caption || !scheduledTime) {
            showError("Please provide a caption and select a scheduled time.");
            return;
        }

        if (!generatedFilename) {
            showError("No generated video found.");
            return;
        }

        hideError();
        scheduleBtn.disabled = true;
        scheduleBtn.querySelector('.btn-text').textContent = "Scheduling...";
        const loader = document.getElementById('schedule-loader');
        if(loader) loader.classList.remove('hidden');

        try {
            const response = await fetch('/schedule', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    filename: generatedFilename,
                    caption: caption,
                    scheduled_time: scheduledTime
                })
            });

            const data = await response.json();
            
            if (!response.ok || !data.success) {
                throw new Error(data.error || 'Scheduling failed');
            }

            scheduleSuccess.classList.remove('hidden');
            
            // Reload page after a delay to show updated schedule
            setTimeout(() => {
                window.location.reload();
            }, 1500);

        } catch (err) {
            showError(err.message);
        } finally {
            scheduleBtn.disabled = false;
            scheduleBtn.querySelector('.btn-text').textContent = "Schedule to Instagram & YouTube";
            if(loader) loader.classList.add('hidden');
        }
    });
});

async function deletePost(id) {
    if (!confirm("Are you sure you want to cancel and delete this scheduled post?")) return;
    
    try {
        const response = await fetch(`/delete_schedule/${id}`, { method: 'POST' });
        const data = await response.json();
        if (!response.ok || !data.success) {
            alert("Error: " + (data.error || "Failed to delete post"));
        } else {
            window.location.reload();
        }
    } catch (err) {
        alert("Error: " + err.message);
    }
}
