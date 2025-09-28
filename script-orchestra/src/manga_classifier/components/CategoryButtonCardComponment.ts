
import {ref, defineComponent} from 'vue';
import type {PropType} from 'vue'
import type {CategoryButton, CategoryButtonCard} from '@/manga_classifier/model/Model'

export default defineComponent({
  name: 'CategoryButtonCardComponment',
  props: {
    buttonCard: {
      type: Object as PropType<CategoryButtonCard>,
      required: true,
    },
    side: {
      type: String as PropType<string>,
      required: true,
    },
    currentFolderPath: {
      type: String as PropType<string>,
      required: true,
    },
  },
  emits: ['folderChange'],
  setup(props, { emit }) {
    const expanded = ref(false)
    const handleButtonClick = (btn: CategoryButton) => {
      emit('folderChange', props.currentFolderPath, btn.folderPath)
    };
    
    return { expanded, handleButtonClick}
  }
});
