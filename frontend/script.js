document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('mappings-form');
    const saveButton = document.getElementById('save-button');
    const statusMessage = document.getElementById('status-message');
    const availableKeysContainer = document.getElementById('available-keys-container');
    const keySelector = document.getElementById('key-selector');
    const addKeyButton = document.getElementById('add-key-button');
    const cancelKeyButton = document.getElementById('cancel-key-button');

    let currentMappings = {};
    let availableKeys = [];
    let targetKeysListElement = null; // Element to add the selected key to

    // --- API Functions ---
    async function fetchMappings() {
        try {
            const response = await fetch('/api/mappings');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            currentMappings = await response.json();
            populateForm();
        } catch (error) {
            showStatus(`Error fetching mappings: ${error.message}`, true);
            console.error('Fetch mappings error:', error);
        }
    }

    async function fetchAvailableKeys() {
         try {
            const response = await fetch('/api/available-keys');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            availableKeys = await response.json();
            populateKeySelector();
        } catch (error) {
            showStatus(`Error fetching available keys: ${error.message}`, true);
            console.error('Fetch available keys error:', error);
        }
    }

    async function saveMappings() {
        const formData = new FormData(form);
        const updatedMappings = {};

        // Reconstruct the mappings object from form data
        for (const action in currentMappings) {
             const type = formData.get(`${action}-type`);
             const keysListElement = form.querySelector(`#${action}-keys`);
             const keys = Array.from(keysListElement.querySelectorAll('.key-pill'))
                             .map(pill => pill.dataset.key);

             updatedMappings[action] = { type, keys };
        }

        console.log("Saving:", updatedMappings); // Debug log

        showStatus('Saving...', false);
        try {
            const response = await fetch('/api/mappings', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(updatedMappings),
            });

            const result = await response.json();

            if (response.ok && result.status === 'success') {
                showStatus('Mappings saved successfully!', false);
                currentMappings = updatedMappings; // Update local cache
            } else {
                throw new Error(result.message || `HTTP error! status: ${response.status}`);
            }
        } catch (error) {
            showStatus(`Error saving mappings: ${error.message}`, true);
            console.error('Save mappings error:', error);
        }
    }

    // --- UI Functions ---
    function populateForm() {
        form.innerHTML = ''; // Clear previous entries
        const sortedActions = Object.keys(currentMappings).sort(); // Sort actions for consistent order

        sortedActions.forEach(action => {
            const mapping = currentMappings[action];
            const entryDiv = document.createElement('div');
            entryDiv.classList.add('mapping-entry');

            const label = document.createElement('label');
            label.htmlFor = `${action}-type`;
            label.textContent = formatActionName(action) + ':';
            entryDiv.appendChild(label);

            // Type Selector (Tap, Press, Release, None)
            const typeSelect = document.createElement('select');
            typeSelect.name = `${action}-type`;
            typeSelect.id = `${action}-type`;
            ['key_tap', 'key_press', 'key_release', 'none'].forEach(type => {
                const option = document.createElement('option');
                option.value = type;
                option.textContent = formatTypeName(type);
                if (type === mapping.type) {
                    option.selected = true;
                }
                typeSelect.appendChild(option);
            });
            entryDiv.appendChild(typeSelect);

            // Keys List Area
            const keysListDiv = document.createElement('div');
            keysListDiv.classList.add('keys-list');
            keysListDiv.id = `${action}-keys`; // ID for finding this element later

            (mapping.keys || []).forEach(key => {
                 keysListDiv.appendChild(createKeyPill(key, keysListDiv));
            });

            // Add '+' Button
             const addButton = document.createElement('button');
             addButton.type = 'button'; // Prevent form submission
             addButton.classList.add('add-key-btn');
             addButton.textContent = '+';
             addButton.title = 'Add key';
             addButton.addEventListener('click', () => openKeySelector(keysListDiv));
             keysListDiv.appendChild(addButton); // Add button inside the keys list


            entryDiv.appendChild(keysListDiv);
            form.appendChild(entryDiv);
        });
    }

     function createKeyPill(key, parentListElement) {
        const pill = document.createElement('span');
        pill.classList.add('key-pill');
        pill.textContent = key;
        pill.dataset.key = key; // Store key name
        pill.title = 'Click to remove';
        pill.tabIndex = 0; // Make focusable

        pill.addEventListener('click', () => {
             parentListElement.removeChild(pill);
        });
         pill.addEventListener('keydown', (e) => {
             if (e.key === 'Enter' || e.key === ' ') {
                  parentListElement.removeChild(pill);
             }
        });
        return pill;
    }

    function formatActionName(action) {
        return action.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
    }
     function formatTypeName(type) {
        switch(type) {
            case 'key_tap': return 'Tap (Press+Release)';
            case 'key_press': return 'Press Only';
            case 'key_release': return 'Release Only';
            case 'none': return 'None';
            default: return type;
        }
    }

    function showStatus(message, isError) {
        statusMessage.textContent = message;
        statusMessage.className = isError ? 'status-error' : 'status-success';
    }

     function populateKeySelector() {
        keySelector.innerHTML = '<option value="">-- Select Key --</option>'; // Default option
        availableKeys.sort().forEach(key => {
            const option = document.createElement('option');
            option.value = key;
            option.textContent = key;
            keySelector.appendChild(option);
        });
    }

    function openKeySelector(targetElement) {
        targetKeysListElement = targetElement; // Store which list to add to
        availableKeysContainer.style.display = 'block';
        keySelector.focus();
    }

    function closeKeySelector() {
        availableKeysContainer.style.display = 'none';
        targetKeysListElement = null;
        keySelector.value = ""; // Reset selector
    }

    function addSelectedKey() {
         const selectedKey = keySelector.value;
         if (selectedKey && targetKeysListElement) {
             // Prevent adding duplicate keys within the same action
             const existingKeys = Array.from(targetKeysListElement.querySelectorAll('.key-pill')).map(p => p.dataset.key);
             if (!existingKeys.includes(selectedKey)) {
                 const newPill = createKeyPill(selectedKey, targetKeysListElement);
                 // Insert pill before the add button
                 const addButton = targetKeysListElement.querySelector('.add-key-btn');
                 targetKeysListElement.insertBefore(newPill, addButton);
             } else {
                 alert(`${selectedKey} is already added to this action.`);
             }
         }
         closeKeySelector();
    }


    // --- Event Listeners ---
    saveButton.addEventListener('click', saveMappings);
    addKeyButton.addEventListener('click', addSelectedKey);
    cancelKeyButton.addEventListener('click', closeKeySelector);

    // --- Initial Load ---
    fetchAvailableKeys(); // Fetch keys first
    fetchMappings(); // Then fetch and populate mappings

});